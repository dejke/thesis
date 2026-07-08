import os
import operator
import utils
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from pathlib import Path
from dotenv import load_dotenv
from prompts import threat_modeler_prompt, strategist_prompt, executor_prompt
import asyncio

from minisweagent.models.litellm_model import LitellmModel
from minisweagent.agents.default import DefaultAgent

from docker_compose_target_env import DockerComposeTargetEnv

""" import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("minisweagent").setLevel(logging.INFO) """
load_dotenv()

HERE = Path(__file__).resolve()
BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")
MAX_EXECUTION_LOOPS =  2
print(BASE_URL)
class RedTeamState(TypedDict):
    target_path: str
    model_output: dict
    logs: Annotated[list[str], operator.add]
    loop_count: int
    current_agent: str

def threat_model_node(state: RedTeamState):

    target_path = state.get("target_path")

    model = LitellmModel(
        model_name = "openai/prisma_gemini_3_flash",
        temperature=0.0,
        model_kwargs={
            "api_base": os.getenv("BASE_URL"),
            "api_key": os.getenv("API_KEY"),
            },
        cost_tracking="ignore_errors"
    )

    environment = DockerComposeTargetEnv(
        target = "juiceshop",
        service = "threat-modeler",
        compose_file=str(HERE.parent.parent / "docker" / "docker-compose.yml")
    )

    system_template = (
    "You are a helpful assistant that can interact with a computer via bash.\n"
    "Respond with exactly one bash code block per turn.\n"
    "When finished, run a command whose first output line is "
    "'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT', followed by your final answer."
    )

    instance_template = "Complete the following task: {{task}}"

    agent = DefaultAgent(
        model=model,
        env=environment,
        step_limit=100,
        system_template=system_template,
        instance_template=instance_template
    )

    try:
        res = agent.run(task="Read the source code at /target-src and construct a detailed threat model of the software")
        print(res)  
        """ for m in agent.messages:
            print(m.get("role"), "->", m.get("content"))
            if "extra" in m and m["extra"].get("actions"):
                print("  actions parsed:", m["extra"]["actions"]) """
    finally:
        environment.cleanup()


    return {"model_output": res}

builder = StateGraph(RedTeamState)


builder.add_node("ThreatModel", threat_model_node)
builder.add_edge(START, "ThreatModel")  
builder.add_edge("ThreatModel", END)

graph = builder.compile()


if __name__ == "__main__":
    initial_input = {
        "model_output": {}, 
        "loop_count": 0,
        "target_path": f"{HERE.parent}/target_src",
        "current_agent": "threat_modeler"
    }

    out = graph.invoke(initial_input)
