from typing import Dict, Any, List


class DockerfileGenerator:
    def __init__(self):
        self.templates = {
            "streamlit": self._streamlit_template,
            "fastapi": self._fastapi_template,
            "flask": self._flask_template,
            "default": self._default_template
        }

    def generate(self, analysis: Dict[str, Any], dependencies: List[str], app_type: str = "default") -> str:
        template_func = self.templates.get(app_type, self._default_template)
        return template_func(dependencies, analysis)

    def _streamlit_template(self, dependencies: List[str], analysis: Dict[str, Any]) -> str:
        python_version = self._detect_python_version(analysis)
        return f"""FROM python:{python_version}-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:{python_version}-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
EXPOSE 8080

CMD ["streamlit", "run", "main.py", "--server.port=8080", "--server.address=0.0.0.0"]
"""

    def _fastapi_template(self, dependencies: List[str], analysis: Dict[str, Any]) -> str:
        python_version = self._detect_python_version(analysis)
        return f"""FROM python:{python_version}-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:{python_version}-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
"""

    def _flask_template(self, dependencies: List[str], analysis: Dict[str, Any]) -> str:
        python_version = self._detect_python_version(analysis)
        return f"""FROM python:{python_version}-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:{python_version}-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
"""

    def _default_template(self, dependencies: List[str], analysis: Dict[str, Any]) -> str:
        python_version = self._detect_python_version(analysis)
        return f"""FROM python:{python_version}-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:{python_version}-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
EXPOSE 8080

CMD ["python", "main.py"]
"""

    def _detect_python_version(self, analysis: Dict[str, Any]) -> str:
        issues = analysis.get("issues", [])
        for issue in issues:
            if "python" in issue.get("description", "").lower():
                if "3.11" in issue.get("description", ""):
                    return "3.11"
                elif "3.10" in issue.get("description", ""):
                    return "3.10"
                elif "3.9" in issue.get("description", ""):
                    return "3.9"
        return "3.11"

    def detect_app_type(self, dependencies: List[str]) -> str:
        deps_lower = [d.lower() for d in dependencies]
        if "streamlit" in deps_lower:
            return "streamlit"
        elif "fastapi" in deps_lower:
            return "fastapi"
        elif "flask" in deps_lower:
            return "flask"
        return "default"
