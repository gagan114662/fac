defmodule Fac.Harness.Evidence do
  @moduledoc """
  Evidence manifest creation and validation for harness engineering.
  """

  @required_fields ~w(head_sha captured_at flows artifacts assertions)

  @doc """
  Create an evidence manifest struct.
  """
  @spec create_manifest(map()) :: map()
  def create_manifest(attrs) when is_map(attrs) do
    %{
      "head_sha" => Map.get(attrs, "head_sha", ""),
      "captured_at" => Map.get(attrs, "captured_at", DateTime.utc_now() |> DateTime.to_iso8601()),
      "flows" => Map.get(attrs, "flows", []),
      "artifacts" => Map.get(attrs, "artifacts", []),
      "assertions" => Map.get(attrs, "assertions", [])
    }
  end

  @doc """
  Validate that an evidence manifest has all required fields and correct types.

  Returns `{:ok, manifest}` if valid, `{:error, errors}` if invalid.
  """
  @spec validate_manifest(map()) :: {:ok, map()} | {:error, list(String.t())}
  def validate_manifest(manifest) when is_map(manifest) do
    errors =
      []
      |> validate_required_fields(manifest)
      |> validate_captured_at(manifest)
      |> validate_flows(manifest)
      |> validate_assertions(manifest)
      |> validate_artifacts(manifest)
      |> Enum.reverse()

    if errors == [] do
      {:ok, manifest}
    else
      {:error, errors}
    end
  end

  def validate_manifest(_), do: {:error, ["manifest must be a map"]}

  defp validate_required_fields(errors, manifest) do
    Enum.reduce(@required_fields, errors, fn field, acc ->
      if Map.has_key?(manifest, field) do
        acc
      else
        ["missing required field '#{field}'" | acc]
      end
    end)
  end

  defp validate_captured_at(errors, manifest) do
    case Map.get(manifest, "captured_at") do
      nil ->
        errors

      value when is_binary(value) ->
        case DateTime.from_iso8601(value) do
          {:ok, _, _} -> errors
          {:error, _} -> ["captured_at must be ISO-8601 timestamp" | errors]
        end

      _ ->
        ["captured_at must be a string" | errors]
    end
  end

  defp validate_flows(errors, manifest) do
    case Map.get(manifest, "flows") do
      nil ->
        errors

      flows when is_list(flows) ->
        if Enum.all?(flows, &is_binary/1) do
          errors
        else
          ["flows must be an array of strings" | errors]
        end

      _ ->
        ["flows must be an array" | errors]
    end
  end

  defp validate_assertions(errors, manifest) do
    case Map.get(manifest, "assertions") do
      nil ->
        errors

      assertions when is_list(assertions) ->
        Enum.with_index(assertions, 1)
        |> Enum.reduce(errors, fn {assertion, idx}, acc ->
          validate_single_assertion(acc, assertion, idx)
        end)

      _ ->
        ["assertions must be an array" | errors]
    end
  end

  defp validate_single_assertion(errors, assertion, idx) when is_map(assertion) do
    required = ~w(name status details)
    missing = Enum.filter(required, fn key -> not Map.has_key?(assertion, key) end)

    errors =
      if missing != [] do
        ["assertion[#{idx}] missing #{Enum.join(missing, "/")}" | errors]
      else
        errors
      end

    case Map.get(assertion, "status") do
      status when status in ["pass", "fail"] -> errors
      nil -> errors
      status -> ["assertion[#{idx}] has invalid status '#{status}'" | errors]
    end
  end

  defp validate_single_assertion(errors, _assertion, idx) do
    ["assertion[#{idx}] must be a map" | errors]
  end

  defp validate_artifacts(errors, manifest) do
    case Map.get(manifest, "artifacts") do
      nil ->
        errors

      artifacts when is_list(artifacts) ->
        Enum.with_index(artifacts, 1)
        |> Enum.reduce(errors, fn {artifact, idx}, acc ->
          validate_single_artifact(acc, artifact, idx)
        end)

      _ ->
        ["artifacts must be an array" | errors]
    end
  end

  defp validate_single_artifact(errors, artifact, idx) when is_map(artifact) do
    required = ~w(path sha256 size_bytes)
    missing = Enum.filter(required, fn key -> not Map.has_key?(artifact, key) end)

    if missing != [] do
      ["artifact[#{idx}]: missing #{Enum.join(missing, ", ")}" | errors]
    else
      errors
    end
  end

  defp validate_single_artifact(errors, _artifact, idx) do
    ["artifact[#{idx}] must be a map" | errors]
  end
end
