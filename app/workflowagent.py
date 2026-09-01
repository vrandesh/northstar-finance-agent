""" 
Workflow implementation for the Northstar Finance Agent.

Utilizes LangGraph for orchestrating the workflow logic.

Strategy/Design: 
1. Nodes run in the following order
 - Intake
 - Retrieve
 - gather
 - Reconcile
 - Explain
2. Then the graph either finishes successfully at a human in loop approval gate or encounters an error at any of the nodes.
3. On Approval, it resumes and submits exactly once
4. LangGraph manages the execution flow and ensures that each node is executed according to the defined strategy.
5. Exception Checkpointer is provided by the LangGraph that ensures a run survives a restart and the interrupted execution can resume from the last checkpoint.
6. Safety Guardrails enforced within the code
"""

import sqlite3
import uuid
from typing import Any, Dict, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from .schemas import (Action, ApprovalRequest, CaseRequest, Fact, Inference, Outcome,
                      Recommendation, ToolResult, ToolStatus)

class State(TypedDict, total=False):
    run_id: str
    raw_case: dict
    case: dict
    retrieved: list
    untrusted_texts: list
    tools: dict
    injection: dict
    recon: dict
    outcome: str
    recommendation: dict
    decision: dict
    status: str
    

# --------------------------------------------------------------------------- #
class Agent: 
    
    def __init__(self):
        self.state: State = {}
        self.run_id: str = str(uuid.uuid4())
        
    # --- nodes to be implemented --- #
    def intake(self):
        pass

    def retrieve(self):
        pass

    def gather(self):
        pass

    def reconcile(self):
        pass

    def explain(self):
        pass
    
    def approval_gate(self):
        pass
    
    def submit(self):
        pass    

    def finalize(self):
        pass    
    
    
    # --- public API endpoints --- # 
    def run_cases(self):
        pass
    
    def start(self, case: dict, run_id: str = None):
        pass
    
    def get(self, run_id: str):
        pass   
    
    def approve(self, run_id: str):
        pass
    
    def evaluate(self, run_id: str):
        pass
    

    # --- helper methods --- # 
    def _load_state(self, run_id: str):
        pass

    def _save_state(self):
        pass