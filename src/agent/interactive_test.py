from sys import argv

from vertexai import agent_engines

from src.config import env


def get_agent(reasoning_engine_id: str):
    return agent_engines.get(f"projects/{env.PROJECT_NUMBER}/locations/{env.LOCATION}/reasoningEngines/{reasoning_engine_id}")


if __name__ == "__main__":
    if len(argv) < 2:
        print("Usage: python interactive_test.py <reasoning_engine_id>")
        exit(1)

    agent = get_agent(argv[1])

    while True:
        query = input("Enter your query: ")
        # TODO: Implementar logica de conversa
