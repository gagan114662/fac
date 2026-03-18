defmodule FacWeb.PageController do
  use FacWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
