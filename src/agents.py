from dataclasses import dataclass, field
from typing import Optional
from prompts import threat_modeler_prompt, strategist_prompt, executor_prompt


@dataclass
class AgentConfig:
    name: str
    model_name: str
    system_prompt: str
    temperature: float
    needs_docker: bool
    task: Optional[str] = None
    step_limit: Optional[int] = None


threat_modeler = AgentConfig(
    name="threat_modeler",
    model_name="openai/prisma_gemini_3_flash",
    system_prompt=threat_modeler_prompt,
    task="Analyze the source code of the target software at {target_path} to produce a threat model",
    temperature=0.7,
    step_limit=20,
    needs_docker=True,
)

strategist = AgentConfig(
    name="strategist",
    model_name="openai/prisma_gemini_3_flash",
    system_prompt=strategist_prompt,
    temperature=0.7,
    step_limit=30,
    needs_docker=False,
)

executor = AgentConfig(
    name="executor",
    model_name="openai/prisma_gemini_3_flash",
    system_prompt=executor_prompt,
    task="Follow the attack strategy below and attempt exploting vulnerabilites:\n{strategy}",
    temperature=0.7,
    step_limit=30,
    needs_docker=True,
)
