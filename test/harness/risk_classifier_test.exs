defmodule Fac.Harness.RiskClassifierTest do
  use ExUnit.Case, async: true

  alias Fac.Harness.RiskClassifier

  describe "normalize_path/1" do
    test "strips leading ./" do
      assert RiskClassifier.normalize_path("./lib/foo.ex") == "lib/foo.ex"
    end

    test "strips leading /" do
      assert RiskClassifier.normalize_path("/lib/foo.ex") == "lib/foo.ex"
    end

    test "converts backslashes" do
      assert RiskClassifier.normalize_path("lib\\foo.ex") == "lib/foo.ex"
    end

    test "trims whitespace" do
      assert RiskClassifier.normalize_path("  lib/foo.ex  ") == "lib/foo.ex"
    end
  end

  describe "path_matches?/2" do
    test "matches glob pattern" do
      assert RiskClassifier.path_matches?("lib/fac/tools/agent.ex", "lib/fac/tools/**")
    end

    test "does not match unrelated path" do
      refute RiskClassifier.path_matches?("test/foo_test.exs", "lib/fac/tools/**")
    end

    test "** matches everything" do
      assert RiskClassifier.path_matches?("anything.txt", "**")
    end

    test "empty pattern returns false" do
      refute RiskClassifier.path_matches?("lib/foo.ex", "")
    end
  end

  describe "classify/2" do
    setup do
      rules = %{
        "high" => ["lib/fac_web/controllers/**", "config/**"],
        "medium" => ["lib/fac/**", "lib/fac_web/**"],
        "low" => ["**"]
      }

      {:ok, rules: rules}
    end

    test "classifies controller changes as high risk", %{rules: rules} do
      assert RiskClassifier.classify(["lib/fac_web/controllers/page_controller.ex"], rules) ==
               "high"
    end

    test "classifies config changes as high risk", %{rules: rules} do
      assert RiskClassifier.classify(["config/runtime.exs"], rules) == "high"
    end

    test "classifies lib changes as medium risk", %{rules: rules} do
      assert RiskClassifier.classify(["lib/fac/repo.ex"], rules) == "medium"
    end

    test "classifies other files as low risk", %{rules: rules} do
      assert RiskClassifier.classify(["README.md"], rules) == "low"
    end

    test "empty file list returns low" do
      assert RiskClassifier.classify([], %{"high" => ["lib/**"]}) == "low"
    end

    test "returns highest matching tier", %{rules: rules} do
      files = ["lib/fac_web/controllers/api.ex", "README.md"]
      assert RiskClassifier.classify(files, rules) == "high"
    end
  end

  describe "load_contract/1" do
    test "loads valid contract" do
      assert {:ok, contract} = RiskClassifier.load_contract("harness/contract.json")
      assert is_map(contract)
      assert Map.has_key?(contract, "version")
      assert Map.has_key?(contract, "riskTierRules")
    end

    test "returns error for missing file" do
      assert {:error, _} = RiskClassifier.load_contract("nonexistent.json")
    end
  end
end
