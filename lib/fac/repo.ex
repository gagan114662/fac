defmodule Fac.Repo do
  use Ecto.Repo,
    otp_app: :fac,
    adapter: Ecto.Adapters.Postgres
end
