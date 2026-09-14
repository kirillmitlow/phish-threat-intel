from typing import Annotated, Sequence, List, Optional, Union, Dict, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from core.ai_client import get_chat_model
from core.config_loader import load_agent_config
from prompts import load_prompt
from tools import get_tools


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


class BaseAgent:

    def __init__(
        self,
        tools: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        llm: Optional[ChatOpenAI] = None,
        verbose: bool = True,
        agent_name: str = "base_agent"
    ):
        self.agent_name = agent_name
        self.tools = tools or []
        self.system_prompt = system_prompt or load_prompt("react_system.md")
        self.llm = llm or get_chat_model()
        self.verbose = verbose

        if self.tools:
            self.model_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.model_with_tools = self.llm

        self.trace_history: List[dict] = []
        self.graph = self._build_graph()

    @classmethod
    def from_config(cls, config_source: Union[str, Dict[str, Any]]) -> "BaseAgent":
        if isinstance(config_source, str):
            config = load_agent_config(config_source)
        else:
            config = config_source

        model_cfg = config.get("model", {})
        model_name = model_cfg.get("name")
        temperature = model_cfg.get("temperature", 0.7)
        llm = get_chat_model(model=model_name, temperature=temperature) if model_name else get_chat_model(temperature=temperature)

        prompt_file = config.get("prompt_file", "react_system.md")
        system_prompt = load_prompt(prompt_file)

        tool_names = config.get("tools", [])
        tools = get_tools(tool_names) if tool_names else []

        verbose = config.get("verbose", True)
        agent_name = config.get("agent_name", "configured_agent")

        return cls(
            tools=tools,
            system_prompt=system_prompt,
            llm=llm,
            verbose=verbose,
            agent_name=agent_name
        )

    def _build_graph(self):
        builder = StateGraph(AgentState)

        def agent_node(state: AgentState):
            messages = state["messages"]
            response = self.model_with_tools.invoke(messages)
            return {"messages": [response]}

        builder.add_node("agent", agent_node)

        if self.tools:
            tool_node = ToolNode(self.tools, handle_tool_errors=True)
            builder.add_node("tools", tool_node)

            builder.add_edge(START, "agent")
            builder.add_conditional_edges("agent", tools_condition)
            builder.add_edge("tools", "agent")
        else:
            builder.add_edge(START, "agent")
            builder.add_edge("agent", END)

        return builder.compile()

    def run(self, user_query: str, max_steps: int = 20) -> str:
        self.trace_history = []
        initial_messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_query)
        ]

        if self.verbose:
            print(f"\n[Agent: {self.agent_name}] Новая задача: {user_query}")
            print("=" * 60)

        final_response_content = ""
        step_counter = 0

        for state_update in self.graph.stream({"messages": initial_messages}, stream_mode="updates"):
            for node_name, update in state_update.items():
                step_counter += 1
                if step_counter > max_steps:
                    print(f"[Agent:{self.agent_name}] Достигнут лимит шагов ({max_steps}), останавливаюсь.")
                    return {"result": final_response_content or "(лимит шагов — без финального ответа)",
                            "trace": self.trace_history}

                messages_list = update.get("messages", [])
                for msg in messages_list:
                    if isinstance(msg, AIMessage):
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                rec = {
                                    "step": step_counter,
                                    "node": node_name,
                                    "kind": "action",
                                    "content": f"Вызов инструмента: {tc['name']}",
                                    "args": dict(tc.get("args", {})),
                                }
                                if msg.content:
                                    rec["thought"] = msg.content.strip()
                                self.trace_history.append(rec)
                                if self.verbose:
                                    print(f"  🛠️  Action: {tc['name']} | args: {tc.get('args')}")
                        elif msg.content:
                            rec = {
                                "step": step_counter,
                                "node": node_name,
                                "kind": "final",
                                "content": msg.content.strip(),
                            }
                            self.trace_history.append(rec)
                            if self.verbose:
                                print(f"  ✅ Final: {msg.content.strip()[:300]}")
                    elif isinstance(msg, ToolMessage):
                        self.trace_history.append({
                            "step": step_counter,
                            "node": node_name,
                            "kind": "observation",
                            "content": str(msg.content)[:3000],
                        })
                        if self.verbose:
                            print(f"  📊 Observation: {str(msg.content)[:300]}")

                if messages_list and isinstance(messages_list[-1], AIMessage) and not messages_list[-1].tool_calls:
                    final_response_content = messages_list[-1].content or final_response_content

        return {"result": final_response_content, "trace": self.trace_history}
