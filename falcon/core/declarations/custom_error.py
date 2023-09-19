from typing import List, TYPE_CHECKING, Optional, Type, Union

from falcon.core.solidity_types import UserDefinedType
from falcon.core.source_mapping.source_mapping import SourceMapping
from falcon.core.variables.local_variable import LocalVariable

if TYPE_CHECKING:
    from falcon.core.compilation_unit import FalconCompilationUnit


class CustomError(SourceMapping):
    def __init__(self, compilation_unit: "FalconCompilationUnit"):
        super().__init__()
        self._name: str = ""
        self._parameters: List[LocalVariable] = []
        self._compilation_unit = compilation_unit

        self._solidity_signature: Optional[str] = None
        self._full_name: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, new_name: str) -> None:
        self._name = new_name

    @property
    def parameters(self) -> List[LocalVariable]:
        return self._parameters

    def add_parameters(self, p: "LocalVariable"):
        self._parameters.append(p)

    @property
    def compilation_unit(self) -> "FalconCompilationUnit":
        return self._compilation_unit

    # region Signature
    ###################################################################################
    ###################################################################################

    @staticmethod
    def _convert_type_for_solidity_signature(t: Optional[Union[Type, List[Type]]]):
        # pylint: disable=import-outside-toplevel
        from falcon.core.declarations import Contract

        if isinstance(t, UserDefinedType) and isinstance(t.type, Contract):
            return "address"
        return str(t)

    @property
    def solidity_signature(self) -> Optional[str]:
        """
        Return a signature following the Solidity Standard
        Contract and converted into address
        :return: the solidity signature
        """
        # Ideally this should be an assert
        # But due to a logic limitation in the solc parsing (find_variable)
        # We need to raise an error if the custom error sig was not yet built
        # (set_solidity_sig was not called before find_variable)
        if self._solidity_signature is None:
            raise ValueError("Custom Error not yet built")
        return self._solidity_signature

    def set_solidity_sig(self) -> None:
        """
        Function to be called once all the parameters have been set

        Returns:

        """
        parameters = [x.type for x in self.parameters]
        self._full_name = self.name + "(" + ",".join(map(str, parameters)) + ")"
        solidity_parameters = map(self._convert_type_for_solidity_signature, parameters)
        self._solidity_signature = self.name + "(" + ",".join(solidity_parameters) + ")"

    @property
    def full_name(self) -> Optional[str]:
        """
        Return the error signature without
        converting contract into address
        :return: the error signature
        """
        if self._full_name is None:
            raise ValueError("Custom Error not yet built")
        return self._full_name

    # endregion
    ###################################################################################
    ###################################################################################

    def __str__(self):
        return "revert " + self.solidity_signature