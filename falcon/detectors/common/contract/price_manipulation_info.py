from typing import List
from falcon.detectors.abstract_detector import AbstractDetector, DetectorClassification
from falcon.utils.output import Output
from falcon.core.declarations import Contract
from falcon.core.variables.state_variable import StateVariable
from falcon.core.declarations import FunctionContract, Modifier
from falcon.core.cfg.node import NodeType, Node
from falcon.core.declarations.event import Event
from falcon.core.expressions import CallExpression, Identifier
from falcon.analyses.data_dependency.data_dependency import is_dependent

from falcon.core.declarations.solidity_variables import (
    SolidityFunction,
)
from falcon.core.variables.local_variable import LocalVariable
from falcon.core.variables.state_variable import StateVariable

from falcon.core.expressions import CallExpression
from falcon.core.expressions.assignment_operation import AssignmentOperation
from falcon.detectors.common.contract.price_manipulation_tools import PriceManipulationTools

from falcon.ir.operations import (
    EventCall,
)

class PriceManipulationInfo(AbstractDetector):
    """
    Detect when `msg.sender` is not used as `from` in transferFrom along with the use of permit.
    """

    ARGUMENT = "price-manipulation-info"
    HELP = "transferFrom uses arbitrary from with permit"
    IMPACT = DetectorClassification.INFORMATIONAL
    CONFIDENCE = DetectorClassification.MEDIUM

    WIKI = " https://metatrust.feishu.cn/wiki/wikcnley0RNMaoaSzdjcCpYxYoD"

    WIKI_TITLE = "The risk of price manipulation in DeFi projects"
    WIKI_DESCRIPTION = (
        "Price manipulation is a common attack in DeFi projects. "
    )
    WIKI_EXPLOIT_SCENARIO = """
        A malicious attacker can manipulate the price of a token by using a fake permit.
    """

    WIKI_RECOMMENDATION = """
        A malicious attacker can manipulate the price of a token by using a fake permit. To prevent this, it is recommended to use the `transferFrom` function with the `from` parameter set to `msg.sender` and the `permit` function to check the validity of the transfer.
    """
    
    ERC20_FUNCTION = [
    "balanceOf(address)",
    "balance",
    "balanceOf"
]

    def checkIfHavePriceManipulation(self, contract: Contract):
        result_dependent_data = []
        result_call_data = []
        if contract.is_interface:
            return result_call_data, result_dependent_data
        for function in contract.functions:
            return_vars = []
            return_vars = self._get_all_return_variables(function)
            return_calls = self._get_all_return_calls(function)
            erc20_vars = []
            erc20_calls = []
            erc20_nodes = []
            for node in function.nodes:
                node_vars, node_calls = self._get_calls_and_var_recursively_node(node)
                if len(node_vars) > 0:
                    erc20_vars.append(node_vars)
                    erc20_calls.append(node_calls)
                    erc20_nodes.append(node)
            all_risk_vars = []
            if return_vars is not None:
                all_risk_vars.extend(return_vars)
            for risk_var in all_risk_vars:
                for dangerous_erc20_vars, dangerous_erc20_calls, node in zip(erc20_vars, erc20_calls, erc20_nodes):
                    for dangerous_erc20_var, dangerous_erc20_call in zip(dangerous_erc20_vars, dangerous_erc20_calls):
                        if is_dependent(risk_var, dangerous_erc20_var, function):
                            result_dependent_data.append([function, risk_var, dangerous_erc20_var, dangerous_erc20_call, node])
            for call in return_calls:
                result_call_data.append([function, call[0], call[1]])
        return result_call_data, result_dependent_data

    @staticmethod
    def _get_all_return_variables(func: FunctionContract):
        ret = []
        for node in func.nodes:
            if node.will_return and len(node.variables_read) > 0:
                ret.extend(node.variables_read)
        ret.extend(func.returns)
        return ret
    
    @staticmethod
    def _get_all_return_calls(func: FunctionContract):
        ret_calls = []
        for node in func.nodes:
            if node.will_return and "require" not in str(node) and hasattr(node, "calls_as_expression") and len(node.calls_as_expression) > 0:
                _, calls = PriceManipulationInfo._get_calls_and_var_recursively_node(node)
                for call in calls:
                    if isinstance(call, SolidityFunction):
                        ret_calls.append((call, node))
                    elif hasattr(call, "called") and ((call.called and hasattr(call.called, "member_name") and call.called.member_name in PriceManipulationInfo.ERC20_FUNCTION) or (call.called and hasattr(call.called, "value") and call.called.value.name in PriceManipulationInfo.ERC20_FUNCTION)):
                        ret_calls.append((call, node))
        return ret_calls

    @staticmethod
    def _get_all_assignment_for_variables(func: FunctionContract):
        variable_assignment = []
        for node in func.nodes:
            if isinstance(node.expression, AssignmentOperation):
                variable_assignment = node.variables_written
            if hasattr(node, "calls_as_expression") and len(node.calls_as_expression) > 0:
                pass

    @staticmethod
    def _get_calls_and_var_recursively_node(node: NodeType):
        ret_calls = []
        ret_vars = []
        variable_writtens = []
        if isinstance(node.expression, AssignmentOperation):
            variable_writtens = node.variables_written
            for var in variable_writtens:
                if var is None:
                    continue
                if "before" in str(var.name).lower() or "after" in str(var.name).lower():
                    return [], []            
        if hasattr(node, "calls_as_expression") and len(node.calls_as_expression) > 0:
                for call in node.calls_as_expression:
                    if PriceManipulationInfo._check_call_can_output(call):
                        if call.called.value.full_name in PriceManipulationInfo.ERC20_FUNCTION:
                            if len(call.arguments) == 1 and not str(call.arguments[0]) in ["address(this)"]:
                                ret_calls.append(PriceManipulationInfo._check_if_can_output_call_info(call))
                        else:
                            ret_calls.extend(PriceManipulationInfo._get_calls_recursively(call.called.value))
                    if call.called and hasattr(call.called, "member_name") and call.called.member_name in PriceManipulationInfo.ERC20_FUNCTION:
                        if len(call.arguments) == 1 and not str(call.arguments[0]) in ["address(this)"]:
                            ret_calls.append(PriceManipulationInfo._check_if_can_output_call_info(call))
        if len(node.internal_calls) > 0 and "address(this)" not in str(node):
            for call in node.internal_calls:
                if call.name == "balance(address)":
                    ret_calls.append(call)
        return variable_writtens, ret_calls
    
    @staticmethod
    def _get_calls_recursively(func: FunctionContract, maxdepth=10):
        ret = []
        if maxdepth <= 0:
            return ret
        if hasattr(func, "calls_as_expressions"):
            if len(func.calls_as_expressions) > 0:
                for call in func.calls_as_expressions:
                    if PriceManipulationInfo._check_call_can_output(call):
                        if str(call.called.value) in PriceManipulationInfo.ERC20_FUNCTION:
                            if len(call.arguments) == 1 and not str(call.arguments[0]) in ["address(this)"]:
                                ret.append(PriceManipulationInfo._check_if_can_output_call_info(call))
                        else:
                            ret.extend(PriceManipulationInfo._get_calls_recursively(call.called.value, maxdepth=maxdepth-1))
                    elif isinstance(call, CallExpression) and call.called and not hasattr(call.called, 'value'):
                        if hasattr(call.called, "member_name") and call.called.member_name in PriceManipulationInfo.ERC20_FUNCTION:
                            if len(call.arguments) == 1 and not str(call.arguments[0]) in ["address(this)"]:
                                ret.append(PriceManipulationInfo._check_if_can_output_call_info(call))
        return ret

    @staticmethod
    def _check_call_can_output(call):
        return isinstance(call, CallExpression) and call.called and hasattr(call.called, 'value') and isinstance(call.called.value, FunctionContract) and not isinstance(call.called.value, Modifier) and not isinstance(call.called.value, Event)
    
    @staticmethod
    def _check_if_can_output_call_info(call):
        argument = call.arguments[0]
        if (hasattr(argument, "value") and (isinstance(argument.value, StateVariable)) or "pair" in str(argument).lower()) or (hasattr(argument, "expression") and hasattr(argument.expression, "value") and ((isinstance(argument.expression.value, StateVariable)) or "pair" in str(argument.expression.value).lower())):
            return call

    def _check_contract_if_uniswap_fork(self, contract: Contract):
        if set(PriceManipulationTools.UNISWAP_PAIR_FUNCTION).issubset(set(contract.functions_declared)) or set(PriceManipulationTools.UNISWAP_ROUTER_FUNCTION).issubset(set(contract.functions_declared)):
            return True
        return False

    def _detect(self) -> List[Output]:
        results: List[Output] = []
        result_dependent_data = []
        result_call_data = []
        info = []
        for c in self.contracts:
            if c.name in PriceManipulationTools.SAFECONTRACTS:
                continue
            if c.is_interface:
                continue
            if self._check_contract_if_uniswap_fork(c):
                continue
            if any(router_name in c.name for router_name in ["Router","router"]):
                continue
            result_call_data, result_dependent_data = self.checkIfHavePriceManipulation(c)
            exist_node = []
            if len(result_dependent_data) > 0 or len(result_call_data) > 0:
                info = ["Potential price manipulation risk:\n"]
                for data in result_dependent_data:
                    if data[4] not in exist_node and not any(isinstance(ir, EventCall) for ir in data[4].irs):
                        info += ["\t- In function ", str(data[0]), "\n",
                            "\t\t-- ", data[4], " have potential price manipulated risk from ", str(data[2]), " and call ", str(data[3]), " which could influence variable:", str(data[1]), "\n"
                        ]
                        exist_node.append(data[4])
                for call in result_call_data:
                    if call[2] not in exist_node and not any(isinstance(ir, EventCall) for ir in call[2].irs):
                        info += ["\t- In function ", str(call[0]), "\n",
                            "\t\t-- ", call[2], "have potential price manipulated risk in return call ", str(call[1]), " could influence return value\n"
                        ]
                        exist_node.append(call[2])
                res = self.generate_result(info)
                results.append(res)
        return results
