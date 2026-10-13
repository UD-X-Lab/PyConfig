python - <<'PY'
import importlib.metadata as md
for ep in md.distribution("mytool-weiwei").entry_points:
    if ep.group == "console_scripts":
        print(ep.name, "->", ep.value)
PY
