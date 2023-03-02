# imports
import json
import os


UPDATE_ENV_YML = "update_env.yml"


def main():
    # get all subfolders
    current_folder = "."
    subfolders = [
        name
        for name in os.listdir(current_folder)
        if os.path.isdir(os.path.join(current_folder, name))
    ]

    notebook_counter = 0
    for folder in subfolders:
        sub_folder = os.path.join(current_folder, folder)
        # file flag to identify the need to generate a dedicated workflow for this particular folder
        dedicated_workflow_generator = "generate_workflow.py"

        if not os.path.exists(os.path.join(sub_folder, dedicated_workflow_generator)):
            # now get the list of notebook files
            nbs = [nb for nb in os.listdir(sub_folder) if nb.endswith(".ipynb")]
            for notebook in nbs:
                # set the cron job schedule to trigger a different hour to avoid any resource contention
                hour_to_trigger = notebook_counter % 24
                day_to_schedule = 2  # Tuesday
                cron_schedule = f"0 {hour_to_trigger} * * {day_to_schedule}"
                write_notebook_workflow(notebook, folder, cron_schedule)
                notebook_counter += 1


def get_validation_yml(notebook_folder, notebook_name):
    validation_yml = ""
    validation_json_file_name = os.path.join(
        notebook_folder, notebook_name.replace(".ipynb", "-validations.json")
    )

    if os.path.exists(validation_json_file_name):
        with open(validation_json_file_name, "r") as json_file:
            validation_file = json.load(json_file)
            for validation in validation_file["validations"]:
                validation_yml += get_validation_check_yml(
                    notebook_folder, notebook_name, validation
                )

    return validation_yml


def get_validation_check_yml(notebook_folder, notebook_name, validation):
    validation_name = validation["name"]
    validation_file_name = validation_name.replace(" ", "_")
    notebook_output_file = notebook_name.replace(".", ".output.")
    full_folder_name = f"v1/python-sdk/tutorials/automl-with-azureml/{notebook_folder}"

    check_yml = f"""
    - name: {validation_name}
      run: |
         python v1/scripts/validation/{validation_file_name}.py \\
                --file_name {notebook_output_file} \\
                --folder {full_folder_name} \\"""

    for param_name, param_value in validation["params"].items():
        if type(param_value) is list:
            check_yml += f"""
                --{param_name} \\"""

            for param_item in param_value:
                param_item_value = param_item.replace("\n", "\\n")
                check_yml += f"""
                  \"{param_item_value}\" \\"""
        else:
            check_yml += f"""
                --{param_name} {param_value} \\"""

    return check_yml[:-2]


def write_notebook_workflow(notebook, notebook_folder, cron_schedule):
    notebook_name = notebook.replace(".ipynb", "")
    creds = "${{secrets.AZ_CREDS}}"
    runner = "${{vars.V1_UBUNTU_RUNNER}}"

    run_update_env = ""
    update_yml_file = f"v1/python-sdk/tutorials/automl-with-azureml/{notebook_folder}/{UPDATE_ENV_YML}"
    # some notebook needs install more packages with the basic automl requirement.
    if os.path.exists(os.path.join(notebook_folder, UPDATE_ENV_YML)):
        run_update_env = f"""
    - name: update conda env with the update_env.yml
      run: |
        conda env update --file {update_yml_file}"""

    validation_yml = get_validation_yml(notebook_folder, notebook)

    workflow_yaml = f"""name: {notebook_name}
# This file is generated by v1/python-sdk/tutorials/automl-with-azureml/generate_workflows.py
on:
  workflow_dispatch:
  schedule:
    - cron: "{cron_schedule}"
  pull_request:
    branches:
      - main
    paths:
      - v1/python-sdk/tutorials/automl-with-azureml/{notebook_folder}/**
      - v1/python-sdk/tutorials/automl-with-azureml/automl_env_linux.yml
      - .github/workflows/python-sdk-tutorial-{notebook_name}.yml
jobs:
  build:
    runs-on: {runner}
    defaults:
      run:
        shell: bash -l {{0}}
    strategy:
      fail-fast: false
    steps:
    - name: check out repo
      uses: actions/checkout@v2
    - name: setup python
      uses: actions/setup-python@v2
      with:
        python-version: "3.8"
    - name: Run Install packages
      run: |
         chmod +x ./v1/scripts/install-packages.sh
         ./v1/scripts/install-packages.sh
      shell: bash
    - name: create automl conda environment
      uses: conda-incubator/setup-miniconda@v2
      with:
          activate-environment: azure_automl
          environment-file: v1/python-sdk/tutorials/automl-with-azureml/automl_env_linux.yml
          auto-activate-base: false{run_update_env}
    - name: install papermill and set up the IPython kernel
      run: |
        pip install papermill==2.4.0
        python -m ipykernel install --user --name azure_automl --display-name "Python (azure_automl)"
        pip list
    - name: azure login
      uses: azure/login@v1
      with:
        creds: {creds}
    - name: Run update-azure-extensions
      run: |
         chmod +x ./v1/scripts/update-azure-extensions.sh
         ./v1/scripts/update-azure-extensions.sh
      shell: bash
    - name: attach to workspace
      run: az ml folder attach -w main -g azureml-examples
    - name: run {notebook}
      run: papermill -k python {notebook} {notebook_name}.output.ipynb
      working-directory: v1/python-sdk/tutorials/automl-with-azureml/{notebook_folder}{validation_yml}
    - name: upload notebook's working folder as an artifact
      if: ${{{{ always() }}}}
      uses: actions/upload-artifact@v2
      with:
        name: {notebook_name}
        path: v1/python-sdk/tutorials/automl-with-azureml/{notebook_folder}\n"""

    workflow_file = (
        f"../../../../.github/workflows/python-sdk-tutorial-{notebook_name}.yml"
    )
    workflow_before = ""
    if os.path.exists(workflow_file):
        with open(workflow_file, "r") as f:
            workflow_before = f.read()

    if workflow_yaml != workflow_before:
        # write workflow
        with open(workflow_file, "w") as f:
            f.write(workflow_yaml)


# run functions
if __name__ == "__main__":
    # call main
    main()
