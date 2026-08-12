from livekit.plugins import facemarket


def test_public_package_identity():
    assert facemarket.__version__ == "0.1.0"
    error = facemarket.APIError(1001, "avatar not found")
    assert error.code == 1001
    assert error.message == "avatar not found"
    assert "1001" in str(error)
