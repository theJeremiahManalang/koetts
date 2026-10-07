"""Shared model identity, so every example uses the same checkpoint."""

MODEL_ID = "ragavsachdeva/magiv3"
# Pin both the weights and executable custom code to a reviewed revision.
# This prevents a future change on the Hub's main branch changing this example.
MODEL_REVISION = "49c73a225122d53adbaa26d53868be81a57706e2"
