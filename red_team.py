import os
import operator
import utils
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage
from claude_agent_sdk import ClaudeAgentOptions, query
from pathlib import Path
from dotenv import load_dotenv
import asyncio


load_dotenv()

utils.set_up_cc()
HERE = Path(__file__).resolve()
BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")
MAX_EXECUTION_LOOPS =  2


model = ChatOpenAI(
    base_url=BASE_URL,  
    api_key=API_KEY,
    model="prisma_gemini_3_flash",
    temperature=0.7,
)

class RedTeamState(TypedDict):
    target_repo_path: str
    model_output: dict
    logs: Annotated[list[str], operator.add]
    loop_count: int
    current_agent: str


async def threat_model_node(state: RedTeamState):

    output = state.get("model_output")

    with open(Path(HERE.parent,"prompts", "tool_users","threat_modeler.md")) as f:
        sp = f.read()

    messages = []

    async for message in query(
        prompt="Scan the target software and make a threat model",
        options=ClaudeAgentOptions(system_prompt=sp,cwd=str(Path(HERE.parent, "target"))),
    ):
       messages.append(message)

    final_msg = messages[-1]

    output["threat_model"] =  final_msg.result
    print(f"THREAT MODEL:\n{final_msg.result}\n\n")
    
    return {"target_repo_path": "target/path", "model_output": output, "logs": ["Threat model: Made a threat model"]}


def strategist_node(state:RedTeamState):

    output = state.get("model_output")
    threat_model = output.get("threat_model")
    report = output.get("executor")
    curr_loops = state.get("loop_count")

    with open(Path(HERE.parent,"prompts","basic", "strategist.md")) as f:
        sp = f.read()

    if curr_loops == 0:
        response = model.invoke([
        SystemMessage(content=sp,cwd=str(Path(HERE.parent, "target"))),
        HumanMessage(content=f"Create an actionable attack plan to exploit the vulnerabilites outlined in the following threat model:\n{threat_model}")
    ])
    else:
        response = model.invoke([
        SystemMessage(content=sp,cwd=str(Path(HERE.parent, "target"))),
        HumanMessage(content=f"Based on the intitial threat model:\n{threat_model}\n,and this execution report:\n{report}\nCome up with a new attack plan")
    ])
        

    output["strategist"]= response.content
    print(f"STRATEGIST:\n{response.content}\n\n")

    return {"model_output": output, "logs": [f"Strategist: {response.content}"]}


async def executor_node(state: RedTeamState):

    output = state.get("model_output")
    strategy = output.get("strategist")
    curr_loops = state.get("loop_count")

    with open(Path(HERE.parent,"prompts", "tool_users","executor.md")) as f:
        sp = f.read()

    messages = []

    async for message in query(
        prompt=f"Follow and execute the following attack plan:\n{strategy}",
        options=ClaudeAgentOptions(system_prompt=sp,cwd=str(Path(HERE.parent, "target"))),
    ):
        messages.append(message)
    
    final_msg = messages[-1]

    output["executor"] =  final_msg.result
    print(f"EXECUTOR:\n{final_msg.result}\n\n")
    
    return {"model_output": output, "logs": ["Executed attack plan"], "loop_count": curr_loops+1}

def should_continue(state:RedTeamState):
    lc = state.get("loop_count")
    if lc < MAX_EXECUTION_LOOPS:
        return "Strategist"
    print("Max loops reached. Exiting")
    return "__end__"
    

builder = StateGraph(RedTeamState)


builder.add_node("ThreatModel", threat_model_node)
builder.add_node("Strategist", strategist_node)
builder.add_node("Executor", executor_node)


builder.add_edge(START, "ThreatModel")       
builder.add_edge("ThreatModel", "Strategist") 
builder.add_edge("Strategist", "Executor") 
      
builder.add_conditional_edges(
    "Executor",
    should_continue,
    {
        "Strategist": "Strategist",  
        "__end__": END               
    }
)

graph = builder.compile()

async def main():
    print("main...")
    initial_input = {
        "model_output": {}, 
        "loop_count": 0,
        "target_repo_path": f"{HERE.parent}/target",
        "current_agent": "threat_modeler"
    }
    
    final_output = await graph.ainvoke(initial_input)
    
    print("Logs:")
    for log in final_output.get("logs"):
        print(log)


if __name__ == "__main__":
    asyncio.run(main())