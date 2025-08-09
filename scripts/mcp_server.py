import argparse
from jsts_debugger.mcp import make_mcp_server

def main():
    """MCP 서버를 실행합니다."""
    parser = argparse.ArgumentParser(description="JSTS Debugger MCP Server")
    parser.add_argument(
        "project_path",
        type=str,
        help="디버깅할 Node.js 프로젝트의 경로",
    )
    args = parser.parse_args()

    mcp_server = make_mcp_server("jsts-debugger", args.project_path)

    print(f"MCP server starting for project at: {args.project_path}")
    mcp_server.run()


if __name__ == "__main__":
    main()
