defmodule Fac.Harness.EvidenceTest do
  use ExUnit.Case, async: true

  alias Fac.Harness.Evidence

  describe "create_manifest/1" do
    test "creates manifest with all fields" do
      manifest =
        Evidence.create_manifest(%{
          "head_sha" => "abc123",
          "flows" => ["app-launch"],
          "artifacts" => [],
          "assertions" => []
        })

      assert manifest["head_sha"] == "abc123"
      assert manifest["flows"] == ["app-launch"]
      assert is_binary(manifest["captured_at"])
    end

    test "uses defaults for missing fields" do
      manifest = Evidence.create_manifest(%{})
      assert manifest["head_sha"] == ""
      assert manifest["flows"] == []
      assert manifest["artifacts"] == []
      assert manifest["assertions"] == []
    end
  end

  describe "validate_manifest/1" do
    test "valid manifest passes" do
      manifest = %{
        "head_sha" => "abc123",
        "captured_at" => "2024-01-01T00:00:00Z",
        "flows" => ["app-launch"],
        "artifacts" => [],
        "assertions" => [
          %{"name" => "test", "status" => "pass", "details" => "ok"}
        ]
      }

      assert {:ok, ^manifest} = Evidence.validate_manifest(manifest)
    end

    test "missing required fields returns errors" do
      assert {:error, errors} = Evidence.validate_manifest(%{})
      assert length(errors) == 5

      assert Enum.any?(errors, &String.contains?(&1, "head_sha"))
      assert Enum.any?(errors, &String.contains?(&1, "captured_at"))
      assert Enum.any?(errors, &String.contains?(&1, "flows"))
      assert Enum.any?(errors, &String.contains?(&1, "artifacts"))
      assert Enum.any?(errors, &String.contains?(&1, "assertions"))
    end

    test "invalid captured_at returns error" do
      manifest = %{
        "head_sha" => "abc",
        "captured_at" => "not-a-date",
        "flows" => [],
        "artifacts" => [],
        "assertions" => []
      }

      assert {:error, errors} = Evidence.validate_manifest(manifest)
      assert Enum.any?(errors, &String.contains?(&1, "ISO-8601"))
    end

    test "invalid flows returns error" do
      manifest = %{
        "head_sha" => "abc",
        "captured_at" => "2024-01-01T00:00:00Z",
        "flows" => [1, 2, 3],
        "artifacts" => [],
        "assertions" => []
      }

      assert {:error, errors} = Evidence.validate_manifest(manifest)
      assert Enum.any?(errors, &String.contains?(&1, "flows"))
    end

    test "assertion with invalid status returns error" do
      manifest = %{
        "head_sha" => "abc",
        "captured_at" => "2024-01-01T00:00:00Z",
        "flows" => [],
        "artifacts" => [],
        "assertions" => [
          %{"name" => "test", "status" => "maybe", "details" => "dunno"}
        ]
      }

      assert {:error, errors} = Evidence.validate_manifest(manifest)
      assert Enum.any?(errors, &String.contains?(&1, "invalid status"))
    end

    test "artifact missing required fields returns error" do
      manifest = %{
        "head_sha" => "abc",
        "captured_at" => "2024-01-01T00:00:00Z",
        "flows" => [],
        "artifacts" => [%{"path" => "test.png"}],
        "assertions" => []
      }

      assert {:error, errors} = Evidence.validate_manifest(manifest)
      assert Enum.any?(errors, &String.contains?(&1, "artifact"))
    end

    test "non-map input returns error" do
      assert {:error, ["manifest must be a map"]} = Evidence.validate_manifest("not a map")
    end
  end
end
