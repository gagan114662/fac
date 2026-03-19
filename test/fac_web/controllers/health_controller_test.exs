defmodule FacWeb.HealthControllerTest do
  use FacWeb.ConnCase

  test "GET /api/health returns ok status", %{conn: conn} do
    conn = get(conn, ~p"/api/health")
    assert %{"status" => "ok", "timestamp" => timestamp, "version" => version} =
             json_response(conn, 200)

    assert is_binary(timestamp)
    assert {:ok, _, _} = DateTime.from_iso8601(timestamp)
    assert is_binary(version)
  end
end
