import vertexai
from vertexai.generative_models import GenerativeModel
from typing import Dict, Any
import json
from app.config import settings


class GeminiService:
    def __init__(self):
        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
        self.model = GenerativeModel(
            model_name=settings.gemini_model,
            generation_config={
                "temperature": settings.gemini_temperature,
                "max_output_tokens": settings.gemini_max_tokens,
            }
        )

    def analyze_notebook(self, notebook_content: str, dependencies: list[str]) -> Dict[str, Any]:
        prompt = f"""Act as a Senior DevOps Engineer and Python Expert. Analyze this Jupyter notebook for production readiness on Google Cloud Run.

NOTEBOOK CODE:
{notebook_content}

DEPENDENCIES:
{', '.join(dependencies)}

Provide a strict analysis in JSON format:
{{
  "cell_classifications": [
    {{"cell_index": 0, "cell_type": "code", "classification": "exploration|training|production|testing", "reasoning": "why this classification"}}
  ],
  "issues": [
    {{"severity": "critical|high|medium|low", "category": "security|performance|compatibility|style", "description": "issue description", "cell_index": 0, "suggestion": "detailed fix"}}
  ],
  "recommendations": ["general recommendation 1", "general recommendation 2"],
  "resource_estimates": {{"cpu": "1", "memory": "512Mi", "estimated_cold_start_ms": 2000}}
}}

CRITICAL CHECKS:
1. SECURITY:
   - Detect hardcoded secrets (API keys, passwords, GCS credentials).
   - Identify 'pickle.load' (insecure deserialization).
   - Flag 'os.system', 'subprocess.call' with user input (command injection).
   - Check for SQL injection patterns in f-strings.

2. CLOUD RUN COMPATIBILITY:
   - Flag local file writes (e.g., 'open("data.csv", "w")') that are not in '/tmp'. Cloud Run filesystem is in-memory and ephemeral.
   - Ensure no hardcoded ports (must use os.environ.get('PORT', 8080)).
   - Identify infinite loops or blocking calls that prevent startup.

3. PERFORMANCE:
   - Flag non-vectorized Pandas operations (iterating rows).
   - Suggest 'parquet' over 'csv' for large datasets.
   - Identify loading huge datasets into memory without 'chunksize'.

4. CODE QUALITY:
   - Flag missing error handling (try/except blocks) for external calls.
   - Identify unused imports or variables."""

        response = self.model.generate_content(prompt)
        result = self._parse_json_response(response.text)
        return result

    def calculate_health_score(self, analysis: Dict[str, Any]) -> int:
        score = 100
        issues = analysis.get('issues', [])

        for issue in issues:
            severity = issue.get('severity', 'low')
            if severity == 'critical':
                score -= 20
            elif severity == 'high':
                score -= 10
            elif severity == 'medium':
                score -= 5
            elif severity == 'low':
                score -= 2

        return max(0, min(100, score))

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "cell_classifications": [],
                "issues": [],
                "recommendations": ["Failed to parse Gemini response"],
                "resource_estimates": {"cpu": "1", "memory": "512Mi", "estimated_cold_start_ms": 3000}
            }
