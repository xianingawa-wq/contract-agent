#!/usr/bin/env bash
set -euo pipefail
python3 -m grpc_tools.protoc \
  -I contract_agent/agent_rpc/proto \
  --python_out=contract_agent/agent_rpc \
  --grpc_python_out=contract_agent/agent_rpc \
  contract_agent/agent_rpc/proto/agent.proto
python3 - <<'PY'
from pathlib import Path

path = Path("contract_agent/agent_rpc/agent_pb2_grpc.py")
content = path.read_text(encoding="utf-8")
old_import = "import agent_pb2 as agent__pb2\n"
new_import = "from contract_agent.agent_rpc import agent_pb2 as agent__pb2\n"
if old_import in content:
    content = content.replace(old_import, new_import, 1)
elif new_import not in content:
    raise RuntimeError("Could not find expected agent_pb2 import in generated gRPC file")
path.write_text(content, encoding="utf-8")
PY
