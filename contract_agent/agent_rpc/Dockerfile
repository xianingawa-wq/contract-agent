FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/contract_agent/agent_rpc:/app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN python3 -m grpc_tools.protoc -I /app/contract_agent/agent_rpc/proto --python_out=/app/contract_agent/agent_rpc --grpc_python_out=/app/contract_agent/agent_rpc /app/contract_agent/agent_rpc/proto/agent.proto
EXPOSE 50051
CMD ["python3", "-m", "contract_agent.agent_rpc.server"]
