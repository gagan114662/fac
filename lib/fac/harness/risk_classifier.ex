defmodule Fac.Harness.RiskClassifier do
  @moduledoc """
  Classifies file paths into risk tiers using glob matching against the harness contract.
  """

  @risk_order ~w(critical high medium low)

  @doc """
  Load and parse the harness contract JSON file.
  """
  @spec load_contract(String.t()) :: {:ok, map()} | {:error, String.t()}
  def load_contract(path \\ "harness/contract.json") do
    case File.read(path) do
      {:ok, content} ->
        case Jason.decode(content) do
          {:ok, contract} when is_map(contract) -> {:ok, contract}
          {:ok, _} -> {:error, "contract root must be a JSON object"}
          {:error, reason} -> {:error, "invalid JSON: #{inspect(reason)}"}
        end

      {:error, reason} ->
        {:error, "cannot read contract: #{inspect(reason)}"}
    end
  end

  @doc """
  Classify a list of changed file paths into a risk tier.

  Returns the highest matching risk tier from the contract's riskTierRules.
  """
  @spec classify(list(String.t()), map()) :: String.t()
  def classify(changed_files, risk_tier_rules) when is_list(changed_files) and is_map(risk_tier_rules) do
    if changed_files == [] do
      "low"
    else
      normalized_files = Enum.map(changed_files, &normalize_path/1)

      result =
        Enum.find(@risk_order, fn tier ->
          patterns = Map.get(risk_tier_rules, tier, [])
          any_path_matches?(normalized_files, patterns)
        end)

      result || "low"
    end
  end

  @doc """
  Normalize a file path: strip leading ./ and /, convert backslashes.
  """
  @spec normalize_path(String.t()) :: String.t()
  def normalize_path(path) do
    path
    |> String.trim()
    |> String.replace("\\", "/")
    |> strip_prefix("./")
    |> strip_prefix("/")
  end

  defp strip_prefix(string, prefix) do
    if String.starts_with?(string, prefix) do
      string |> String.trim_leading(prefix) |> strip_prefix(prefix)
    else
      string
    end
  end

  @doc """
  Check if a path matches a glob pattern.
  """
  @spec path_matches?(String.t(), String.t()) :: boolean()
  def path_matches?(path, pattern) do
    normalized_path = normalize_path(path)
    normalized_pattern = normalize_path(pattern)

    if normalized_pattern == "" do
      false
    else
      match_glob?(normalized_path, normalized_pattern)
    end
  end

  defp any_path_matches?(paths, patterns) do
    Enum.any?(paths, fn path ->
      Enum.any?(patterns, fn pattern ->
        path_matches?(path, pattern)
      end)
    end)
  end

  defp match_glob?(path, "**") do
    path != ""
  end

  defp match_glob?(path, pattern) do
    # Convert glob pattern to regex
    regex_str =
      pattern
      |> String.replace(".", "\\.")
      |> String.replace("**/", "(.+/)?")
      |> String.replace("**", ".*")
      |> String.replace("*", "[^/]*")
      |> String.replace("?", "[^/]")

    case Regex.compile("^#{regex_str}$") do
      {:ok, regex} -> Regex.match?(regex, path)
      {:error, _} -> false
    end
  end
end
