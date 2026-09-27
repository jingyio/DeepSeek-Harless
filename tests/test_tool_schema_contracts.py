import unittest

from src.adapters.dsh_trajectory import ToolContract
from src.adapters.tool_schema_contracts import bind_mcp_descriptions


class ToolSchemaContractTests(unittest.TestCase):
    def test_bind_current_mcp_description_without_changing_execution_contract(self):
        contract = ToolContract(("query",), True, ("id",))
        schemas = {"tools": [{"name": "search", "description": "Search papers by topic",
                              "inputSchema": {"type": "object",
                                              "properties": {"query": {"type": "string"}},
                                              "required": ["query"]}}]}
        bound = bind_mcp_descriptions({"search": contract}, schemas)
        self.assertEqual(bound["search"].description, "Search papers by topic")
        self.assertEqual(bound["search"].required_params, contract.required_params)
        self.assertEqual(bound["search"].output_fields, contract.output_fields)
        schemas["tools"][0]["inputSchema"]["required"] = []
        with self.assertRaisesRegex(ValueError, "does not match"):
            bind_mcp_descriptions({"search": contract}, schemas)


if __name__ == "__main__":
    unittest.main()
