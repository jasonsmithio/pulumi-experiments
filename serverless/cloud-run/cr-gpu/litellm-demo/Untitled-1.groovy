# Generated with the go/corp-run CLI

locals {
  project_id     = "nps-ce-team-dev"
  default_region = "us-central1"
}

module "corp_run_standard_infra" {
  source = "../../../modules/corp_run/standard_infra/v0"
  name   = "cr-infra"
  cert_domains = [
    "nps-ce-team-dev.gclb.goog",
    "nps-ce-team-dev.corp.goog",
    "default-npsce-dev.gclb.goog",
    "apps-npsce-dev.gclb.goog",
    "dashboard-npsce-dev.gclb.goog",
    "architect-npsce-dev.gclb.goog",
    "requests-npsce-dev.gclb.goog",
    "experts-npsce-dev.gclb.goog",
    "ai-npsce-dev.gclb.goog",
    "cr-npsce-dev.gclb.goog",
    "k8s-npsce-dev.gclb.goog",
    "devops-npsce-dev.gclb.goog",
    "agents-npsce-dev.gclb.goog",
    "demos.npsce-dev.gclb.goog",
    "adriangraham.npsce-dev.gclb.goog",
    "alanpoole.npsce-dev.gclb.goog",
    "alexmattson.npsce-dev.gclb.goog",
    "ripka.npsce-dev.gclb.goog",
    "ddobrin.npsce-dev.gclb.goog",
    "giovanejr.npsce-dev.gclb.goog",
    "jamieduncan.npsce-dev.gclb.goog",
    "jasondel.npsce-dev.gclb.goog",
    "mbychkowski.npsce-dev.gclb.goog",
    "robedwards.npsce-dev.gclb.goog",
    "meillier.npsce-dev.gclb.goog",
    "sudheerg.npsce-dev.gclb.goog",
    "civerson.npsce-dev.gclb.goog",
    "evekhm.npsce-dev.gclb.goog",
    "gregbray.npsce-dev.gclb.goog",
    "ishmeetm.npsce-dev.gclb.goog",
    "jaysmith.npsce-dev.gclb.goog",
    "kenthua.npsce-dev.gclb.goog",
    "chilm.npsce-dev.gclb.goog",
    "murriel.npsce-dev.gclb.goog",
    "willsulzer.npsce-dev.gclb.goog",
    "yannipeng.npsce-dev.gclb.goog",
    "zsais.npsce-dev.gclb.goog",
    "mcolumbus.npsce-dev.gclb.goog",
  ]
  #svc_name = "default"
  url_mask = "<service>-npsce-dev.gclb.goog"
  region   = local.default_region

  depends_on = [google_project_iam_member.team_iam]
}

module "infra" {
  source = "../../modules/infra"
  # some_variable = ...

  depends_on = [google_project_iam_member.team_iam]
}

data "google_project" "project" {
  project_id = local.project_id
}
