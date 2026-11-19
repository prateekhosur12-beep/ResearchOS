"""Lab 5: Assignment 1 -- Add a Fourth, Discoverable Capability
Adds 'list_files' resource capability to the server manifest.
The MCPClient discovers and invokes 'list_files' dynamically through the manifest,
without any hard-coded methods in the client class.
"""

MOCK_FILES = {
    "README.md": "Agentic AI Systems - mini MCP server demo.",
    "config.json": '{"mode": "debug", "version": "1.0.0"}',
    "notes.txt": "Review chapter 4 on Memory and Context.",
}

# Manifest updated with the 4th capability
CAPABILITIES = [
    {"name": "read_file", "kind": "resource",
     "input": {"path": "str"}, "output": {"content": "str"}},
    {"name": "list_files", "kind": "resource",
     "input": {}, "output": {"files": "list"}},
    {"name": "call_api", "kind": "tool",
     "input": {"endpoint": "str"}, "output": {"data": "any"}},
]

class DynamicMCPServer:
    def list_capabilities(self):
        return CAPABILITIES

    def read_file(self, path):
        if path not in MOCK_FILES:
            return {"error": f"file not found: {path}"}
        return {"content": MOCK_FILES[path]}

    def list_files(self):
        """Newly added discoverable capability."""
        return {"files": list(MOCK_FILES.keys()), "count": len(MOCK_FILES)}

    def call_api(self, endpoint):
        return {"data": f"response from {endpoint}"}

class GenericMCPClient:
    def __init__(self, server, caller_name):
        self.server = server
        self.caller_name = caller_name

    def discover(self):
        return self.server.list_capabilities()

    def call(self, capability_name, **kwargs):
        manifest = {c["name"]: c for c in self.discover()}
        if capability_name not in manifest:
            raise ValueError(f"Capability '{capability_name}' not found in manifest!")
        method = getattr(self.server, capability_name)
        return method(**kwargs)

if __name__ == "__main__":
    server = DynamicMCPServer()
    client = GenericMCPClient(server, caller_name="research_agent")

    print("=== Dynamic Discovery ===")
    caps = client.discover()
    for c in caps:
        print(f"Discovered: {c['name']} ({c['kind']})")

    print("\n=== Invoking Newly Discovered 'list_files' Capability ===")
    file_list = client.call("list_files")
    print("Result:", file_list)

    print("\n=== Reading One of the Listed Files ===")
    content = client.call("read_file", path=file_list["files"][1])
    print(f"Content of {file_list['files'][1]}:", content)
