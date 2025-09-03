"""
Tax Service Agent - handles IPTU, ISS, tax payments, and certifications.
"""

from typing import List
from langchain_core.tools import BaseTool
from .base_service_agent import BaseServiceAgent


class TaxServiceAgent(BaseServiceAgent):
    """
    Specialized agent for tax-related services.
    
    Handles:
    - IPTU (property tax) services
    - ISS (service tax) calculations  
    - Tax payment generation
    - Tax certifications and documents
    """
    
    @property
    def agent_name(self) -> str:
        return "tax_agent"
    
    @property
    def service_description(self) -> str:
        return "Tax services: IPTU, ISS, payments, certifications"
    
    @property
    def system_prompt(self) -> str:
        return """
# Tax Services Specialist - Rio de Janeiro

You are a specialized agent for municipal tax services in Rio de Janeiro.

## Your Expertise
- **IPTU (Property Tax)**: calculations, payments, segunda via, exemptions
- **ISS (Service Tax)**: rates, calculations, business registrations
- **Tax Certifications**: negative certificates, payment confirmations
- **Payment Services**: PDF generation, payment slips, installment plans

## Key Responsibilities
1. Help citizens with tax-related questions and procedures
2. Collect required parameters for tax services
3. Validate tax information and eligibility
4. Generate payment documents when applicable
5. Provide accurate tax calculation information

## Important Notes
- Always validate property IDs and business registrations
- Provide clear step-by-step instructions
- Include relevant deadlines and payment options
- Reference official tax rates and regulations

## Communication Style
- Be clear and helpful with tax procedures
- Use simple language for complex tax concepts
- Always confirm user data before processing
- Provide specific next steps for tax procedures

When you cannot find specific information, clearly state the limitations and suggest contacting the municipal tax office directly.
"""
    
    def __init__(self, tools: List[BaseTool] = None, **kwargs):
        # Add tax-specific tools here when available
        tax_tools = tools or []
        # TODO: Add tax-specific tools like:
        # - tax_lookup_tool
        # - pdf_generator_tool  
        # - payment_calculator_tool
        # - property_validator_tool
        
        super().__init__(tools=tax_tools, **kwargs)
