"""Lab 5: Assignment 2 -- Scope read_file to a Safe Directory
Adds a directory-jail permission boundary: read_file can only access paths
inside the declared safe directory ('/safe/').
Includes an adversarial test attempting to escape the jail, verifying structured rejection.
"""

SANDBOX_STORAGE = {
    "/safe/reports/q1.txt": "Q1 performance: all metrics nominal.",
    "/safe/docs/guide.md": "User guide for campus agent.",
    "/etc/shadow": "root:$6$secretpasswordhashes",
    "/home/user/.ssh/id_rsa": "PRIVATE KEY DATA",
}

class JailedMCPServer:
    SAFE_PREFIX = "/safe/"

    def read_file(self, path):
        # Path validation: normalize and check prefix
        if not path.startswith(self.SAFE_PREFIX) or ".." in path:
            return {
                "error": f"Security Violation: path '{path}' is outside permitted directory '{self.SAFE_PREFIX}'",
                "blocked": True,
                "path": path
            }
        
        if path not in SANDBOX_STORAGE:
            return {"error": f"File not found: '{path}'", "blocked": False}
            
        return {"content": SANDBOX_STORAGE[path], "blocked": False}

if __name__ == "__main__":
    server = JailedMCPServer()

    print("=== Legitimate Read within Safe Directory ===")
    legit = server.read_file("/safe/reports/q1.txt")
    print(f"Read '/safe/reports/q1.txt': {legit}")

    print("\n=== Adversarial Test 1: Absolute Path Escape (/etc/shadow) ===")
    adv1 = server.read_file("/etc/shadow")
    print(f"Read '/etc/shadow': {adv1}")
    assert adv1["blocked"] is True, "Security boundary breached on /etc/shadow!"

    print("\n=== Adversarial Test 2: Directory Traversal (/safe/../home/user/.ssh/id_rsa) ===")
    adv2 = server.read_file("/safe/../home/user/.ssh/id_rsa")
    print(f"Read traversal path: {adv2}")
    assert adv2["blocked"] is True, "Security boundary breached on path traversal!"

    print("\nConfirmed: Permission boundary successfully enforces safe directory access.")
