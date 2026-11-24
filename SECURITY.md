# Security

## Report a vulnerability

Please do not open a public issue for a security defect.

Send the report to support@parazun.com. Write what an attacker could do,
what they need, and the steps to reproduce it. We will reply to the
address.

## What this repository holds

This repository holds the source of the `parazun` command line client. It
holds no secret and no customer data:

- The credentials of a customer live in `~/.config/parazun/credentials.json`
  on the machine of the customer. The file is readable by the owner alone.
  The repository ignores the file name, so a clone cannot commit it.
- The client sends the credential in the `Authorization` header of a
  request. It never writes a credential into a log, a message or a report.
- The tests never touch the network and never use a real credential.

## The scope of a report

A report is in scope when it shows that a customer can read the credential
of another customer, that a customer can use a credential that is not
theirs, or that the client sends a credential to a place it should not.

A defect of the API behind the client is a report for the API, not for
this repository.
