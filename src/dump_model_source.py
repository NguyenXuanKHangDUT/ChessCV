import inspect
from pathlib import Path

import torchvision.models.resnet as resnet_module
import torchvision.models.convnext as convnext_module


ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

OUTPUT_DIR = (
    ROOT
    / "models"
    / "source"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# RESNET SOURCE
# ============================================================

resnet_source = inspect.getsource(
    resnet_module
)

resnet_file = (
    OUTPUT_DIR
    / "torchvision_resnet_full_source.py"
)

resnet_file.write_text(
    resnet_source,
    encoding="utf-8"
)


# ============================================================
# CONVNEXT SOURCE
# ============================================================

convnext_source = inspect.getsource(
    convnext_module
)

convnext_file = (
    OUTPUT_DIR
    / "torchvision_convnext_full_source.py"
)

convnext_file.write_text(
    convnext_source,
    encoding="utf-8"
)


print("Saved:")
print(resnet_file)
print(convnext_file)