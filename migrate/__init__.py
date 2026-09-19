"""Migration package for scanning, classifying, and translating existing AI configs."""

from migrate.scanner import scan_project, ScannedItem
from migrate.classifier import classify_items, ClassifiedItem, ClassificationScope
from migrate.translator import translate_project, MigrationReport

__all__ = [
    "scan_project",
    "ScannedItem",
    "classify_items",
    "ClassifiedItem",
    "ClassificationScope",
    "translate_project",
    "MigrationReport",
]
