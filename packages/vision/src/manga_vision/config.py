"""Reviewed model identity shared by all inference adapters."""

MODEL_ID = "ragavsachdeva/magiv3"
# Pin both the weights and executable custom code to a reviewed revision.
# This prevents a future change on the Hub's main branch changing inference behavior.
MODEL_REVISION = "49c73a225122d53adbaa26d53868be81a57706e2"
