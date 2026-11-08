FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "uagents>=0.25.5" openai pymongo
COPY agent.py README.md ./
EXPOSE 8000
CMD ["python", "-u", "agent.py"]
