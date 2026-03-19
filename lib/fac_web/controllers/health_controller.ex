defmodule FacWeb.HealthController do
  use FacWeb, :controller

  @version Mix.Project.config()[:version]

  def index(conn, _params) do
    json(conn, %{
      status: "ok",
      timestamp: DateTime.utc_now() |> DateTime.to_iso8601(),
      version: @version
    })
  end
end
