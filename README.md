# fvtt-autopublish
A tool & Github Action to automatically publish new versions of a FoundryVTT package to foundryvtt.com

# Using as a Tool
TBW

# Using as a GitHub Action
1.  Log into the Foundry VTT module administration page and navigate to your module's configuration page.
3.  In your browser's URL bar, make note of the number after the "/packages/package/" path segments. This number is your module's _ID_.
4.  Add your Foundry username, password, and your module's ID as secrets to your Github repository:
    ![Secrets Configuration Page](https://user-images.githubusercontent.com/524596/152662901-fb26208b-1678-4e8e-af86-adaef1ab9b3d.png)
5.  Add the following step to your workflow file. Note that this assumes the following:
      - Your workflow has created a GitHub release with attached "module.json" and "module.zip" files.
      - The `RELEASE_NAME` environment variable contains the name of the GitHub release you want to publish.
      - The `MANIFEST_FILE_PATH` environment variable contains the local path to your module's manifest file.
      - The `FOUNDRY_ADMIN_USERNAME` secret contains your Foundry VTT username.
      - The `FOUNDRY_ADMIN_PASSWORD` secret contains your Foundry VTT password.
      - The `FOUNDRY_ADMIN_MODULE_ID` secret contains the your module's ID.
    ```yaml
      # Publish the release to FoundryVTT's package repository.
      - name: Publish Module to FoundryVTT Website
        uses: Varriount/fvtt-autopublish@latest
        with:
          username: ${{ secrets.FOUNDRY_ADMIN_USERNAME }}
          password: ${{ secrets.FOUNDRY_ADMIN_PASSWORD }}
          module-id: ${{ secrets.FOUNDRY_ADMIN_MODULE_ID }}
          manifest-url: https://github.com/${{ github.repository }}/releases/download/${{ env.RELEASE_NAME }}/module.json
          manifest-file: ${{ env.MANIFEST_FILE_PATH }}
    ```
