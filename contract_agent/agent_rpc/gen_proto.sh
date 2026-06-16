#!/usr/bin/env bash
set -euo pipefail
python3 -m grpc_tools.protoc \
  -I contract_agent/agent_rpc/proto \
  --python_out=contract_agent/agent_rpc \
  --grpc_python_out=contract_agent/agent_rpc \
  contract_agent/agent_rpc/proto/agent.proto
