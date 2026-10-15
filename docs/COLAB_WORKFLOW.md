# Moving changes between this repository and Colab

GitHub is the meeting point. Edits made locally and edits made in Colab both reach the
canonical notebook through GitHub commits, never by uploading or downloading files by hand.

## Golden rules
1. **One editor at a time.** Before editing in Colab, push local work. Before editing locally, pull Colab's commits.
2. **Always open the notebook from GitHub in Colab**, never from a stale Drive copy.
3. **Colab saves to the `phishtriage-colab` branch only**, never directly to `main`.
4. **Check before overwriting.** Compare the latest commit on GitHub with what you are about to save.

## Local → Colab
```bash
git switch phishtriage-colab
git status                                # make sure only intended changes are present
git add notebooks/PhishTriage_Colab.ipynb # stage explicitly
git commit -m "Describe the change"
git push origin phishtriage-colab
```
Then, in Colab: *File → Open notebook → GitHub* → `nishtrip14/PhishTriage`, branch
`phishtriage-colab` → `notebooks/PhishTriage_Colab.ipynb`. Tick *Include private repos*
if the repository is private.

## Colab → repository
1. In Colab: *File → Save a copy in GitHub*.
   - Repository `nishtrip14/PhishTriage`, branch `phishtriage-colab`.
   - Path: `notebooks/PhishTriage_Colab.ipynb`.
   - Use a descriptive commit message.
   - Untick *Include a link to Colaboratory* if you don't want the badge cell added.
2. Before saving, open the branch on github.com and confirm that the latest commit is the one
   you started from. If someone or something pushed in the meantime, save under a temporary path
   such as `notebooks/PhishTriage_Colab.colab-<date>.ipynb` instead, then merge locally.
3. Locally:
   ```bash
   git switch phishtriage-colab
   git status                        # commit or stash local edits first
   git pull --ff-only origin phishtriage-colab
   ```
   If `--ff-only` fails, local and Colab work have diverged. Don't force-push.
   Inspect the difference with `git log --oneline --graph --all`, then merge by hand.

## Handing a Colab run back for verification
1. In Colab: *File → Download → Download .ipynb* after the run.
2. Put the file in `colab_import/` in the repository. That folder is git-ignored, because executed outputs can
   contain personal data.
3. Its source cells are compared with the canonical notebook, and its outputs are checked for secrets and
   personal data. Only then are results recorded in `COLAB_STATUS.md`, or a sanitized copy saved to `reports/`.

## Producing the demonstration copy
1. In Colab: *Runtime → Restart and run all* on the canonical notebook.
2. Check that the outputs contain no secrets, tokens, personal email contents or absolute Drive paths.
3. *File → Save a copy in GitHub* to `reports/PhishTriage_Colab_Executed.ipynb`.
4. Record the run date and the source notebook commit in `COLAB_STATUS.md`.

## Secrets in Colab
Use the key icon (*Secrets*) and `from google.colab import userdata; userdata.get("NAME")`.
Never print secrets or write them to files inside the repository.
