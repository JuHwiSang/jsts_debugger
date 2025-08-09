import pytest
import tempfile
import json
from pathlib import Path
from jsts_debugger.mcp import make_mcp_server

@pytest.fixture(scope="session")
def test_project():
    """
    Creates a temporary directory with a simple ts project.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        
        # package.json
        (project_path / "package.json").write_text(json.dumps({
            "name": "test-project",
            "version": "1.0.0",
            "type": "module",
            "main": "index.ts"
        }))
        
        # tsconfig.json
        (project_path / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {
                "module": "NodeNext",
                "moduleResolution": "NodeNext",
                "target": "ES2022",
                "lib": ["ES2022"],
                "esModuleInterop": True,
                "allowSyntheticDefaultImports": True,
                "skipLibCheck": True,
                "allowImportingTsExtensions": True,
            },
            "include": ["**/*.ts"]
        }))
        
        # index.ts
        (project_path / "index.ts").write_text("""
export async function main() {
    debugger;
    const a = 1;
    const b = 2;
    debugger;
    console.log('Hello from test project!');
}
""")
        
        yield str(project_path)


@pytest.fixture(scope="module")
def mcp_server(test_project):
    """
    Creates an MCP server instance for the test project.
    This fixture is module-scoped, so the server is reused across tests in the same module.
    """
    return make_mcp_server("test-debugger", test_project)
