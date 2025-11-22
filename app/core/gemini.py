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
  "model_info": {{
    "has_model": true,
    "model_variable": "name of the trained model variable",
    "model_type": "type of model library and class",
    "n_features": 0,
    "feature_names": [],
    "output_type": "classification|regression|clustering|other",
    "n_classes": null,
    "class_names": [],
    "prediction_method": "predict|predict_proba|forward|transform",
    "input_shape": [],
    "preprocessing_steps": []
  }},
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
   - Identify unused imports or variables.

5. MODEL ANALYSIS (IMPORTANT):
   - Detect if code trains a machine learning model (.fit(), .train(), model compilation)
   - Identify the model variable name (e.g., 'clf', 'model', 'pipeline', 'regressor')
   - Determine model library (sklearn, keras, pytorch, xgboost, lightgbm, etc.)
   - Count input features from X_train.shape, feature columns, or input_dim
   - Detect output type: classification (predict_proba, classes), regression (continuous), clustering (fit_predict)
   - Extract class names from code if present (iris.target_names, label_encoder.classes_, etc.)
   - Identify prediction method used (.predict, .predict_proba, .forward, .transform)
   - Note any preprocessing (StandardScaler, MinMaxScaler, PCA, etc.)"""

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

    def generate_fastapi_app(self, notebook_content: str, model_info: Dict[str, Any]) -> str:
        """Generate a FastAPI application based on the notebook analysis"""
        prompt = f"""You are an expert Python developer. Convert this Jupyter Notebook code into a production-ready FastAPI application.

NOTEBOOK CODE:
{notebook_content}

MODEL INFORMATION:
{json.dumps(model_info, indent=2)}

REQUIREMENTS:
1. Create a FastAPI app.
2. Include the necessary code from the notebook to initialize/load the model variable identified in 'model_info'. 
   - If the notebook trains a model, include that logic (or a simplified version if possible) so the 'model' variable is available.
   - If the notebook loads a model, keep that logic.
   - Ensure the model variable is named consistently.
3. Create a Pydantic model for the input data based on 'model_info' (n_features, feature_names, etc.).
   - If feature names are unknown, use generic names (f1, f2, etc.) or a list of floats.
4. Create a '/predict' endpoint (POST).
   - It should accept the Pydantic model.
   - It should convert input to the format expected by the model (e.g., numpy array, dataframe).
   - It should return the prediction.
5. Handle imports properly.
6. Name the FastAPI instance 'app'.
7. Do NOT include any 'if __name__ == "__main__":' block or 'uvicorn.run' call. This will be handled by the deployment system.
8. Ensure the code is clean and handles errors.

OUTPUT FORMAT:
Return ONLY the Python code for the 'main.py' file. Do not use markdown blocks like ```python. Just the code.
"""
        response = self.model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith('```python'):
            text = text[9:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        return text.strip()

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
                "model_info": {"has_model": False},
                "issues": [],
                "recommendations": ["Failed to parse Gemini response"],
                "resource_estimates": {"cpu": "1", "memory": "512Mi", "estimated_cold_start_ms": 3000}
            }
