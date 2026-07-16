# Individual Contributor License Agreement

**Version 1.0**

Thank you for your interest in contributing to the Paperless Genie project ("the Project"),
maintained by Jegors Čemisovs ("the Project Owner", [github.com/rabestro](https://github.com/rabestro)).

This Contributor License Agreement ("Agreement") documents the rights You grant to the
Project Owner for Your Contributions to the repository in which this file is stored.
It protects You as a contributor as well as the Project Owner; it does not change Your
rights to use Your own Contributions for any other purpose. Please read it carefully
before signing.

## 1. Definitions

- **"You"** (or **"Your"**) means the individual who Submits a Contribution to the Project.
- **"Contribution"** means any original work of authorship — source code, documentation,
  configuration, test data, or other material — that You Submit to the Project.
- **"Submit"** means any form of electronic communication sent to the Project or its
  maintainers, including pull requests, patches, and issue attachments, but excluding
  communication that You conspicuously mark "Not a Contribution".

## 2. Grant of Copyright License

You retain ownership of the copyright in Your Contribution.

Subject to the terms of this Agreement, You grant the Project Owner a perpetual,
worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to
reproduce Your Contribution, prepare derivative works of it, publicly display it,
publicly perform it, sublicense it, and distribute it and such derivative works.

This license expressly includes the right to license and relicense Your Contribution,
in whole or in part, under any license terms the Project Owner chooses — including
copyleft, permissive, and proprietary or commercial licenses.

*Plain-language note (not a limitation of the grant above): the Project follows an
open-core model. The public repositories remain available under their published
open-source licenses, and Your Contribution always stays available under the
repository's open-source license; this clause additionally preserves the Project
Owner's ability to offer the Project under other terms, such as combining it with
closed-source modules or commercial offerings.*

## 3. Grant of Patent License

Subject to the terms of this Agreement, You grant the Project Owner and recipients of
software distributed by the Project Owner a perpetual, worldwide, non-exclusive,
no-charge, royalty-free, irrevocable (except as stated in this section) patent license
to make, have made, use, offer to sell, sell, import, and otherwise transfer the work
to which Your Contribution belongs, where such license applies only to those patent
claims licensable by You that are necessarily infringed by Your Contribution alone or
by combination of Your Contribution with the work to which it was Submitted. If any
entity institutes patent litigation against You or any other entity alleging that Your
Contribution, or the work to which You contributed, constitutes direct or contributory
patent infringement, then any patent licenses granted to that entity under this
Agreement for that Contribution or work terminate as of the date such litigation is
filed.

## 4. Your Representations

You represent that:

1. You are legally entitled to grant the licenses above.
2. Each of Your Contributions is Your original creation.
3. If Your employer has rights to intellectual property that You create — which may
   include Your Contribution — You have received permission to make the Contribution
   on behalf of that employer, or Your employer has waived such rights for the
   Contribution.
4. If Your Contribution includes work that is not Your original creation, You will
   Submit it with complete details of its source and of any license or other
   restriction of which You are aware, conspicuously marked as third-party material.

You agree to notify the Project Owner if You become aware of any facts that would make
these representations inaccurate.

## 5. No Obligation and No Warranty

You are not expected to provide support for Your Contribution, except to the extent
You desire to provide it. Unless required by applicable law or agreed to in writing,
Your Contribution is provided "AS IS", without warranties or conditions of any kind.
The Project Owner is under no obligation to accept, use, or retain any Contribution.

## 6. How to Sign

Signing is self-service and happens in Your first pull request:

1. Read this Agreement.
2. Append an entry for yourself to the `signatures` array in
   [`.github/cla-signatures.json`](.github/cla-signatures.json) in the same pull request as your first contribution:

   ```json
   { "github": "your-github-username", "name": "Your Full Name", "date": "YYYY-MM-DD", "claVersion": "1.0" }
   ```

3. The commit adding your entry constitutes your electronic signature of this
   Agreement, and the git history serves as the signature record.

The `claVersion` field records which version of this Agreement you signed. If the
Agreement is revised, the registry's top-level version is bumped, and you will be
asked to re-sign (add an updated entry) before your next contribution is accepted.

The `CI: CLA` status check verifies the entry automatically and will fail the pull
request until a signature matching the current Agreement version is present.
