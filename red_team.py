import os
import operator
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.store.memory import InMemoryStore
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

HERE = Path(__file__).resolve()
BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")


model = ChatOpenAI(
    base_url=BASE_URL,  
    api_key=API_KEY,
    model="prisma_gemini_3_flash",
    temperature=0.0,
)

class RedTeamState(TypedDict):
    target_repo_path: str
    model_output: dict
    logs: Annotated[list[str], operator.add]
    loop_count: int

class AgentState(TypedDict):
    conversation_history: list[str]

def threat_model_node(state: RedTeamState):

    model_out = "This is a threat model xyz"
    output = state.get("model_output")
    output["threat_model"] =  model_out
    
    return {"target_repo_path": "target/path", "model_output": output, "logs": ["Threat model: Made a threat model"]}

def strategist_node(state:RedTeamState):

    output = state.get("model_output")
    threat_model = output.get("threat_model")
    curr_loops = state.get("loop_count")

    if curr_loops == 0:
        model_out = "Initial attack strategy abc"
    else:
        model_out = f"Revised attack strategy version {curr_loops+1}"

    output["strategist"]= model_out


    return {"model_output": output, "logs": [f"Strategist: {model_out}\n(based on threat model: {threat_model})"]}

def executor_node(state:RedTeamState):

    output = state.get("model_output")
    strategy = output.get("strategist")
    curr_loops = state.get("loop_count")

    model_out = "This is an execution report"
    output["executor"]= model_out

    return {"model_output": output, "logs":[f"Followed attack strategy:\n{strategy}\nExecution report: {model_out}"], "loop_count": curr_loops+1}

def should_continue(state:RedTeamState):
    lc = state.get("loop_count")
    if lc < 3:
        print(f"Looping ({lc})")
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

if __name__ == "__main__":
    initial_input = {
        "model_output": {}, 
        "loop_count": 0
    }
    
    final_output = graph.invoke(initial_input)
    
    print("Logs:")
    for log in final_output.get("logs"):
        print(log)