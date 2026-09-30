def test_modules_import():
    import claude_client
    import lambda_function
    assert callable(lambda_function.lambda_handler)
    assert callable(claude_client.ask)
