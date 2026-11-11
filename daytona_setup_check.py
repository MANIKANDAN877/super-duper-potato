import os
import sys


def main() -> int:
    api_key = os.getenv("DAYTONA_API_KEY")
    if not api_key:
        print("DAYTONA_API_KEY is missing.")
        print("Create one here: https://app.daytona.io/dashboard/keys")
        print("Then set it in the shell or in a local .env file before running this script.")
        return 1

    try:
        from daytona import Daytona, DaytonaConfig

        config = DaytonaConfig(api_key=api_key)
        client = Daytona(config)
        sandbox = client.create()
        print("Sandbox created successfully.")

        response = sandbox.process.code_run('print("Hello World from Daytona sandbox")')
        print("Exit code:", response.exit_code)
        print("Result:", response.result)

        sandbox.delete()
        print("Sandbox deleted successfully.")
        return 0
    except Exception as exc:  # pragma: no cover - user-facing guidance
        message = str(exc)
        print("Sandbox creation failed.")
        print(message)
        print("If the message says the organization does not have a default region, set the default region in the Daytona dashboard and retry.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
