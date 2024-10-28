# TFC State Backup

This is a working prototype of a Terraform Cloud Webook handling Lambda.

TFC has two kinds of webhooks, notifications and run tasks. Run tasks are geared toward adding stages to your run (the user sees these stages and callbacks are used to report status to the UI). Notifications are geared toward asynchronous, behind the scenes stuff. I wrote code to handle either kind. For the first use case here we use notifications to ensure that the terraform state in TFC is backed up to our own AWS account in S3 once an apply is complete (i.e. a new state file has been persisted in TFC).

I started this work from a fork using Terraform https://github.com/bneutra/terraform-state-backer-upper. For reasons I won't go into I further developed the idea using SAM instead (but that other repo is a good reference if you want to use terraform). This repo:
- has the state backup part done by a separate lambda, invoked by the webhook handling Lambda (idea: the webhook Lambda could handle many kinds of events and act as a router to other Lambdas to act on the events)
- streams the state file to disk first (the previous version could encounter memory issues)

```
sam build
sam deploy --parameter-overrides Environment=foo-test S3Bucket=yourbucket-name
```