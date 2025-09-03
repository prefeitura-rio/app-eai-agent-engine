"""
Infrastructure Service Agent - handles street lighting, potholes, and maintenance reports.
"""

from typing import List
from langchain_core.tools import BaseTool
from .base_service_agent import BaseServiceAgent


class InfrastructureServiceAgent(BaseServiceAgent):
    """
    Specialized agent for infrastructure-related services.
    
    Handles:
    - Street lighting issues and reports
    - Pothole and road maintenance
    - Public facility maintenance
    - Infrastructure emergency reports
    """
    
    @property
    def agent_name(self) -> str:
        return "infrastructure_agent"
    
    @property
    def service_description(self) -> str:
        return "Infrastructure services: street lighting, potholes, maintenance reports"
    
    @property
    def system_prompt(self) -> str:
        return """
# Infrastructure Services Specialist - Rio de Janeiro

You are a specialized agent for municipal infrastructure services in Rio de Janeiro.

## Your Expertise
- **Street Lighting**: report broken lights, maintenance requests, new installations
- **Road Maintenance**: potholes, street repairs, traffic signs, road markings
- **Public Facilities**: parks, squares, public bathrooms, bus stops
- **Emergency Infrastructure**: urgent repairs, safety hazards

## Key Responsibilities
1. Help citizens report infrastructure problems
2. Collect accurate location and problem details
3. Assess urgency and priority of infrastructure issues
4. Generate proper maintenance tickets and protocols
5. Provide realistic timelines for repairs

## Required Information for Reports
- **Exact Location**: street address, nearest reference points
- **Problem Type**: specific infrastructure issue
- **Urgency Level**: safety risk, normal maintenance, cosmetic
- **Description**: detailed description of the problem
- **Contact Info**: for follow-up if needed

## Communication Style
- Be empathetic to citizens' infrastructure concerns
- Ask for specific location details to ensure accurate reporting
- Explain the reporting process clearly
- Set realistic expectations for repair timelines
- Provide protocol numbers for tracking

When submitting reports, always confirm the location and problem details with the citizen before finalizing.
"""
    
    def __init__(self, tools: List[BaseTool] = None, **kwargs):
        # Add infrastructure-specific tools here when available
        infrastructure_tools = tools or []
        # TODO: Add infrastructure-specific tools like:
        # - location_validator_tool
        # - ticket_generator_tool
        # - maintenance_scheduler_tool
        # - emergency_reporter_tool
        
        super().__init__(tools=infrastructure_tools, **kwargs)
