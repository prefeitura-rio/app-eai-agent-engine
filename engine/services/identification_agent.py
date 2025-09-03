"""
User Identification Service Agent

This agent handles user identification collection and validation using a conversational approach.
This is for comparison with the workflow-based user_identification_workflow.
"""

import re
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_cloud_sql_pg import PostgresSaver
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from typing_extensions import Annotated, TypedDict


class IdentificationState(TypedDict):
    """State for user identification agent"""
    messages: Annotated[list[BaseMessage], add_messages]
    cpf: Optional[str]
    email: Optional[str]
    name: Optional[str]
    current_step: str
    validation_errors: list[str]
    is_complete: bool


@tool
def validate_cpf_agent(cpf: str) -> Dict[str, Any]:
    """
    Validate Brazilian CPF format and check digits.
    
    Args:
        cpf: CPF string to validate
        
    Returns:
        Dict with validation result and formatted CPF
    """
    # Remove non-digits
    cpf_clean = re.sub(r'\D', '', cpf)
    
    # Check length
    if len(cpf_clean) != 11:
        return {
            "valid": False,
            "error": "CPF deve ter 11 dígitos",
            "formatted_cpf": None
        }
    
    # Check for repeated digits
    if cpf_clean == cpf_clean[0] * 11:
        return {
            "valid": False,
            "error": "CPF inválido - todos os dígitos são iguais",
            "formatted_cpf": None
        }
    
    # Calculate check digits
    def calculate_digit(cpf_partial: str, weights: list) -> int:
        total = sum(int(digit) * weight for digit, weight in zip(cpf_partial, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
    
    # Validate first check digit
    first_digit = calculate_digit(cpf_clean[:9], list(range(10, 1, -1)))
    if int(cpf_clean[9]) != first_digit:
        return {
            "valid": False,
            "error": "CPF inválido - primeiro dígito verificador incorreto",
            "formatted_cpf": None
        }
    
    # Validate second check digit
    second_digit = calculate_digit(cpf_clean[:10], list(range(11, 1, -1)))
    if int(cpf_clean[10]) != second_digit:
        return {
            "valid": False,
            "error": "CPF inválido - segundo dígito verificador incorreto",
            "formatted_cpf": None
        }
    
    # Format CPF
    formatted = f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}"
    
    return {
        "valid": True,
        "error": None,
        "formatted_cpf": formatted
    }


@tool
def validate_email_agent(email: str) -> Dict[str, Any]:
    """
    Validate email format and check domain.
    
    Args:
        email: Email string to validate
        
    Returns:
        Dict with validation result
    """
    # Basic email regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return {
            "valid": False,
            "error": "Formato de email inválido"
        }
    
    # Check for common domains
    domain = email.split('@')[1].lower()
    common_domains = ['gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'uol.com.br']
    
    return {
        "valid": True,
        "error": None,
        "is_common_domain": domain in common_domains
    }


@tool
def validate_name_agent(name: str) -> Dict[str, Any]:
    """
    Validate name format (must have at least first and last name).
    
    Args:
        name: Full name string to validate
        
    Returns:
        Dict with validation result
    """
    name_clean = name.strip()
    
    if len(name_clean) < 2:
        return {
            "valid": False,
            "error": "Nome muito curto"
        }
    
    name_parts = name_clean.split()
    
    if len(name_parts) < 2:
        return {
            "valid": False,
            "error": "Por favor, forneça nome completo (nome e sobrenome)"
        }
    
    # Check if all parts have at least 2 characters
    for part in name_parts:
        if len(part) < 2:
            return {
                "valid": False,
                "error": "Cada parte do nome deve ter pelo menos 2 caracteres"
            }
    
    return {
        "valid": True,
        "error": None,
        "formatted_name": name_clean.title()
    }


@tool
def check_user_registration_agent(cpf: str, email: str) -> Dict[str, Any]:
    """
    Check if user is already registered in the system.
    
    Args:
        cpf: User's CPF
        email: User's email
        
    Returns:
        Dict with registration status
    """
    # Simulate database check
    # In real implementation, this would query the municipal database
    
    # For demo, we'll simulate some registered users
    registered_users = {
        "123.456.789-01": {
            "name": "João Silva Santos",
            "email": "joao.silva@gmail.com"
        },
        "987.654.321-00": {
            "name": "Maria Oliveira Costa",
            "email": "maria.oliveira@hotmail.com"
        }
    }
    
    if cpf in registered_users:
        user_data = registered_users[cpf]
        return {
            "registered": True,
            "name": user_data["name"],
            "email_matches": user_data["email"].lower() == email.lower(),
            "registered_email": user_data["email"]
        }
    
    return {
        "registered": False,
        "name": None,
        "email_matches": False,
        "registered_email": None
    }


class IdentificationAgent:
    """
    Service Agent for User Identification.
    
    This agent uses a conversational approach to collect and validate
    user identification information (CPF, email, name).
    
    Uses the same PostgreSQL checkpointer as the main agent to share memory.
    """
    
    def __init__(self, model: str = "gemini-2.5-flash", checkpointer=None):
        self.model = model
        self.llm = ChatVertexAI(model_name=model, temperature=0.3)
        self.checkpointer = checkpointer or MemorySaver()  # Fallback to MemorySaver
        
        # Bind tools to LLM
        self.llm_with_tools = self.llm.bind_tools([
            validate_cpf_agent,
            validate_email_agent, 
            validate_name_agent,
            check_user_registration_agent
        ])
        
        # Create graph
        self.graph = self._create_graph()
        self.app = self.graph.compile(checkpointer=self.checkpointer)
    
    def _create_graph(self) -> StateGraph:
        """Create the identification agent graph"""
        
        def agent_node(state: IdentificationState) -> IdentificationState:
            """Main agent reasoning node"""
            
            # Create system prompt based on current step
            system_prompt = self._get_system_prompt(state)
            
            # Get last user message
            messages = state["messages"]
            if messages:
                last_message = messages[-1]
            else:
                last_message = HumanMessage(content="Olá, preciso me identificar")
            
            # Create messages for LLM
            llm_messages = [
                AIMessage(content=system_prompt),
                last_message
            ]
            
            # Get LLM response
            response = self.llm_with_tools.invoke(llm_messages)
            
            # Update state
            updated_state = state.copy()
            updated_state["messages"] = [response]
            
            return updated_state
        
        def should_continue(state: IdentificationState) -> str:
            """Determine next step based on state"""
            
            last_message = state["messages"][-1]
            
            # Check if agent wants to use tools
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                return "tools"
            
            # Check if identification is complete
            if state.get("is_complete", False):
                return END
            
            # Continue conversation
            return "agent"
        
        def tools_node(state: IdentificationState) -> IdentificationState:
            """Execute tool calls"""
            
            last_message = state["messages"][-1]
            updated_state = state.copy()
            
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                for tool_call in last_message.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    # Execute tool
                    if tool_name == "validate_cpf_agent":
                        result = validate_cpf_agent.invoke(tool_args)
                        if result["valid"]:
                            updated_state["cpf"] = result["formatted_cpf"]
                            updated_state["current_step"] = "email"
                        else:
                            updated_state["validation_errors"].append(result["error"])
                    
                    elif tool_name == "validate_email_agent":
                        result = validate_email_agent.invoke(tool_args)
                        if result["valid"]:
                            updated_state["email"] = tool_args["email"]
                            updated_state["current_step"] = "registration_check"
                        else:
                            updated_state["validation_errors"].append(result["error"])
                    
                    elif tool_name == "validate_name_agent":
                        result = validate_name_agent.invoke(tool_args)
                        if result["valid"]:
                            updated_state["name"] = result["formatted_name"]
                            updated_state["current_step"] = "complete"
                            updated_state["is_complete"] = True
                        else:
                            updated_state["validation_errors"].append(result["error"])
                    
                    elif tool_name == "check_user_registration_agent":
                        result = check_user_registration_agent.invoke(tool_args)
                        if result["registered"]:
                            if result["email_matches"]:
                                updated_state["name"] = result["name"]
                                updated_state["current_step"] = "complete"
                                updated_state["is_complete"] = True
                            else:
                                updated_state["current_step"] = "name"
                        else:
                            updated_state["current_step"] = "name"
            
            return updated_state
        
        # Create graph
        graph = StateGraph(IdentificationState)
        
        # Add nodes
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        
        # Add edges
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
        
        return graph
    
    def _get_system_prompt(self, state: IdentificationState) -> str:
        """Get system prompt based on current state"""
        
        current_step = state.get("current_step", "cpf")
        cpf = state.get("cpf")
        email = state.get("email")
        validation_errors = state.get("validation_errors", [])
        
        base_prompt = """Você é um assistente especializado em identificação de usuários para serviços municipais.
        
Sua tarefa é coletar e validar as seguintes informações do usuário:
1. CPF (formato: xxx.xxx.xxx-xx)
2. Email
3. Nome completo (nome e sobrenome)

Seja educado, claro e eficiente. Use as ferramentas de validação disponíveis.
"""
        
        if validation_errors:
            base_prompt += f"\n\nErros de validação anteriores: {', '.join(validation_errors)}"
        
        if current_step == "cpf" and not cpf:
            return base_prompt + "\n\nPasso atual: Solicite o CPF do usuário e valide usando validate_cpf_agent."
        
        elif current_step == "email" and cpf and not email:
            return base_prompt + f"\n\nCPF coletado: {cpf}\nPasso atual: Solicite o email do usuário e valide usando validate_email_agent."
        
        elif current_step == "registration_check" and cpf and email:
            return base_prompt + f"\n\nCPF: {cpf}\nEmail: {email}\nPasso atual: Verifique se o usuário está registrado usando check_user_registration_agent."
        
        elif current_step == "name" and cpf and email:
            return base_prompt + f"\n\nCPF: {cpf}\nEmail: {email}\nPasso atual: Solicite o nome completo do usuário e valide usando validate_name_agent."
        
        elif current_step == "complete":
            return base_prompt + f"\n\nIdentificação completa!\nCPF: {cpf}\nEmail: {email}\nNome: {state.get('name')}"
        
        return base_prompt
    
    def run(self, message: str) -> Dict[str, Any]:
        """
        Run the identification agent with a user message.
        
        Args:
            message: User input message
            
        Returns:
            Dict with agent response and current state
        """
        
        # Create initial state
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "cpf": None,
            "email": None,
            "name": None,
            "current_step": "cpf",
            "validation_errors": [],
            "is_complete": False
        }
        
        # Run agent
        config = {"configurable": {"thread_id": "identification_session"}}
        result = self.app.invoke(initial_state, config)
        
        # Extract response
        if result["messages"]:
            response_content = result["messages"][-1].content
        else:
            response_content = "Erro interno do agente"
        
        return {
            "response": response_content,
            "cpf": result.get("cpf"),
            "email": result.get("email"),
            "name": result.get("name"),
            "is_complete": result.get("is_complete", False),
            "current_step": result.get("current_step"),
            "validation_errors": result.get("validation_errors", [])
        }


def create_identification_agent(checkpointer=None) -> IdentificationAgent:
    """Factory function to create identification agent with shared checkpointer"""
    return IdentificationAgent(checkpointer=checkpointer)


if __name__ == "__main__":
    # Test the identification agent
    agent = create_identification_agent()
    
    # Test conversation
    test_messages = [
        "Olá, preciso me identificar",
        "Meu CPF é 123.456.789-01",
        "Meu email é joao.silva@gmail.com"
    ]
    
    for message in test_messages:
        print(f"\nUser: {message}")
        result = agent.run(message)
        print(f"Agent: {result['response']}")
        print(f"State: CPF={result['cpf']}, Email={result['email']}, Complete={result['is_complete']}")
