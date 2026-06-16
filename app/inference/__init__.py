"""Job de inferencia batch (Chronos-T5 + corrección ML).

Reúne la lógica pesada del PoC para correr de forma programada, precomputar las
predicciones de los 12 centros y persistirlas en DynamoDB.
"""
