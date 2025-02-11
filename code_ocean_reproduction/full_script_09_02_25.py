# <editor-fold desc="load libraries">
import numpy as np
import os
import pandas as pd
import torchvision
import torch
import torch.nn as nn
import torchmetrics
import json
from itertools import product
from torchvision import datasets
from torchvision.transforms import ToTensor
from datetime import date
import time
import random
import zipfile

import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams["mathtext.fontset"] = "cm"

device = (
    "cuda"
    if torch.cuda.is_available()
    else "mps"
    if torch.backends.mps.is_available()
    else "cpu"
)
print(f"Using {device} device")

from genomic_benchmarks.dataset_getters.pytorch_datasets import get_dataset


# </editor-fold>


# <editor-fold desc="unzip data">
data_dir = "/data"
output_dir = "/results"
data_unzipped_dir = os.path.join(output_dir, "data_unzipped")
os.mkdir(data_unzipped_dir)

zip_data_files = ["cxr_pneumonia", "OCT", "ptbxl_ecgs"]
for file_i in zip_data_files:
    source_filename =os.path.join(data_dir, file_i) + ".zip"
    target_filename = os.path.join(data_unzipped_dir, file_i)
    if not os.path.exists(target_filename):
        with zipfile.ZipFile(source_filename, "r") as zip_ref:
            zip_ref.extractall(data_unzipped_dir)
    
            

# </editor-fold>

# <editor-fold desc="utility functions">
def identity_func(x):
    return x


def rec_listdir(dir):
    paths = []
    for root, directories, filenames in os.walk(dir):
        for filename in filenames:
            paths.append(os.path.join(root, filename))
    return paths


def compute_metrics(yhat, y):
    y = torch.squeeze(y).to('cpu')
    yhat = torch.squeeze(yhat).to('cpu')
    num_classes = y.shape[1]
    y = torch.argmax(y, dim=1)
    yhat_argmax = torch.argmax(yhat, dim=1)
    auc = torchmetrics.AUROC(task="multiclass", num_classes=num_classes, average="macro")(yhat, y)
    acc = torchmetrics.Accuracy(task="multiclass", num_classes=num_classes, average="macro")(yhat_argmax, y)
    recall = torchmetrics.Recall(task="multiclass", num_classes=num_classes, average="macro")(yhat_argmax, y)
    prec = torchmetrics.Precision(task="multiclass", num_classes=num_classes, average="macro")(yhat_argmax, y)
    f1 = torchmetrics.F1Score(task="multiclass", num_classes=num_classes, average="macro")(yhat_argmax, y)

    out = torch.stack([auc, acc, recall, prec, f1])

    return out


def expand_grid(dictionary):
    return pd.DataFrame([row for row in product(*dictionary.values())],
                        columns=dictionary.keys())


def standardise_fn(x, dim=0):
    x_ = torch.clone(x.detach())
    mu = x_.mean(dim=dim, keepdims=True)
    x_ -= mu
    s = x_.std(dim=dim, keepdims=True) + 1 / len(x_)
    x_ /= s
    return x_


def mean_sd_func(x):
    mu = x.mean()
    sd = x.std()
    out = f"{mu:.2f} \u00B1 {sd:.3f}"
    return out


def mean_sd_func2(x):
    mu = (x * 100).mean()
    sd = (x * 100).std()
    out = f"{mu:.1f} \u00B1 {sd:.1f}"
    return out


ACGT_mapping = dict(zip("ACGTN", range(5)))
ACGT_eye = torch.eye(5, dtype=torch.bool)[:, :4]


def dna_to_onehot(x):
    x_ = [ACGT_mapping[i] for i in x]
    x_ = ACGT_eye[x_]
    return x_


date_today = date.today().strftime("%d_%m_%y")
if not os.path.exists("tables"):
    os.mkdir('tables')

# </editor-fold>

# <editor-fold desc="File Management">

def extract_xy(df_i, resize_transform, diagnosis_labels, mode=torchvision.io.ImageReadMode.GRAY):
    x = []

    for file_i in df_i.img_file:
        x_i = torchvision.io.read_image(file_i, mode=mode)
        x_i = resize_transform(x_i).type(torch.float)
        x.append(x_i)
    x = torch.stack(x)
    x = x / 255.
    x = x.permute((0, 2, 3, 1))

    y = torch.tensor(pd.get_dummies(df_i.diagnosis, columns=diagnosis_labels).to_numpy(),
                     dtype=torch.float)

    return x, y


def load_dataset(dataset_i,
                 channels_last=True,
                 toy_dataset=False,
                 img_size=128,
                 data_dir=data_unzipped_dir,
                 ):
    resize_transform = torchvision.transforms.Resize(size=(img_size, img_size))

    if dataset_i == "FashionMNIST":
        training_data = datasets.FashionMNIST(
            root="data",
            train=True,
            download=True,
            transform=ToTensor(),
        )

        test_data = datasets.FashionMNIST(
            root="data",
            train=False,
            download=True,
            transform=ToTensor(),
        )

        # load train data
        X_train = []
        y_train = []
        for i in range(len(training_data)):
            x_i, y_i = training_data.__getitem__(i)
            X_train.append(x_i)
            y_train.append(y_i)
        X_train = torch.stack(X_train)
        Y_train = torch.eye(10)[y_train].type(torch.float32)
        X_train = torch.flatten(X_train, start_dim=1)

        # load test data
        X_test = []
        y_test = []
        for i in range(len(test_data)):
            x_i, y_i = test_data.__getitem__(i)
            X_test.append(x_i)
            y_test.append(y_i)
        X_test = torch.stack(X_test)
        X_test = torch.flatten(X_test, start_dim=1)
        Y_test = torch.eye(10)[y_test].type(torch.float32)

    if dataset_i == 'human_nontata_promoters':
        dset_train = get_dataset(dataset_i, split='train', version=0)
        dset_test = get_dataset(dataset_i, split='test', version=0)

        X_train, Y_train = zip(*dset_train)
        X_train = [dna_to_onehot(i) for i in X_train]
        X_train = torch.stack(X_train)
        X_train = X_train.type(torch.float)
        Y_train = torch.tensor(Y_train)[:, None].type(torch.float)

        X_test, Y_test = zip(*dset_test)
        X_test = [dna_to_onehot(i) for i in X_test]
        X_test = torch.stack(X_test)
        X_test = X_test.type(torch.float)
        Y_test = torch.tensor(Y_test)[:, None].type(torch.float)

        mu_train = X_train.mean(dim=0, keepdims=True)
        sd_train = X_train.std(dim=0, keepdims=True) + 0.001
        X_train = (X_train - mu_train) / sd_train
        X_test = (X_test - mu_train) / sd_train

    if dataset_i == 'ptbxl_mi':

        # file management
        ptbxl_npy_dir = os.path.join(data_dir, 'npy')
        os.path.exists(ptbxl_npy_dir)

        ptbxl_key_file = '/data/scp_statements.csv'
        ptbxl_keys = pd.read_csv(ptbxl_key_file)
        ptbxl_keys.rename(columns={ptbxl_keys.columns[0]: "code"}, inplace=True)
        all_dx_classes = ptbxl_keys.diagnostic_class.unique()[:-1].tolist()
        dx_label_names = {i: set(ptbxl_keys.code.loc[ptbxl_keys.diagnostic_class == i].to_list()) for i in
                          all_dx_classes}
        selected_dx_codes = ['STTC', 'NORM', 'MI', 'HYP', 'CD']

        # create binary vectors for each outcome class
        ptbxl_label_file = '/data/ptbxl_database.csv'
        ptbxl_labels = pd.read_csv(ptbxl_label_file)
        ptbxl_labels['npy_file'] = [os.path.join(ptbxl_npy_dir, os.path.basename(i)) + '.npy' for i in
                                    ptbxl_labels.filename_lr]
        all_scp_code_dicts = [json.loads(i.replace("\'", "\"")) for i in ptbxl_labels.scp_codes]
        all_scp_code_dicts = [{x: y for x, y in dic_i.items() if y == 100} for dic_i in all_scp_code_dicts]
        all_scp_codes = [list(i.keys()) for i in all_scp_code_dicts]
        unique_scp_codes = set(i for scp_code_i in all_scp_codes for i in scp_code_i)

        for subcode_i in unique_scp_codes:
            ptbxl_labels[subcode_i] = [subcode_i in j for j in all_scp_code_dicts]
        for code_i in selected_dx_codes:
            ptbxl_labels[code_i] = ptbxl_labels[list(dx_label_names[code_i])].any(axis=1)

        outcome_i = "MI"
        confirmed_patients = ptbxl_labels[['NORM', outcome_i]].any(axis=1)

        ptbxl_labels = ptbxl_labels.loc[confirmed_patients, :].reset_index()
        train_df = ptbxl_labels.loc[ptbxl_labels.strat_fold <= 9].reset_index()
        test_df = ptbxl_labels.loc[ptbxl_labels.strat_fold == 10].reset_index()

        if toy_dataset:
            train_df = train_df[:100]
            test_df = test_df[:100]

        X_train = torch.tensor(np.stack([np.load(i) for i in train_df.npy_file])).type(torch.float)
        X_test = torch.tensor(np.stack([np.load(i) for i in test_df.npy_file])).type(torch.float)
        Y_train = torch.tensor(train_df[outcome_i].to_numpy())[:, None].type(torch.float)
        Y_test = torch.tensor(test_df[outcome_i].to_numpy())[:, None].type(torch.float)

        mu_train = X_train.mean(dim=(0, 1), keepdims=True)
        sd_train = X_train.std(dim=(0, 1), keepdims=True) + 0.001
        X_train = (X_train - mu_train) / sd_train
        X_test = (X_test - mu_train) / sd_train

    if dataset_i == "oct":  # https://data.mendeley.com/datasets/rscbjbr9sj/3

        all_files = rec_listdir(os.path.join(data_dir, "OCT"))
        all_files = [i for i in all_files if os.path.basename(i) != ".DS_Store"]
        all_files_basenames = [os.path.basename(i) for i in all_files]
        img_metadata = pd.DataFrame({
            "img_file": all_files,
            "patient_id": [i.split("-")[1] for i in all_files_basenames],
            "diagnosis": [i.split("-")[0] for i in all_files_basenames],
            "repeat": [i.split("-")[2][:-5] for i in all_files_basenames],
            "train_idx": ["train" in i for i in all_files]
        })
        img_metadata = img_metadata.loc[~img_metadata.patient_id.duplicated()].reset_index(drop=True)
        img_metadata = img_metadata.loc[img_metadata.diagnosis.isin(["NORMAL", "CNV"])].reset_index(drop=True)
        diagnosis_labels = ["NORMAL", "CNV"]
        img_metadata.diagnosis = pd.Categorical(img_metadata.diagnosis, categories=diagnosis_labels)

        train_df = img_metadata.loc[img_metadata.train_idx].reset_index(drop=True)
        test_df = img_metadata.loc[~img_metadata.train_idx].reset_index(drop=True)

        X_train, Y_train = extract_xy(train_df,
                                      resize_transform=resize_transform,
                                      diagnosis_labels=diagnosis_labels)
        X_test, Y_test = extract_xy(test_df,
                                    resize_transform=resize_transform,
                                    diagnosis_labels=diagnosis_labels)

    if dataset_i == "cxr":  # https://data.mendeley.com/datasets/rscbjbr9sj/3

        all_files = rec_listdir(os.path.join(data_dir, "cxr_pneumonia"))
        all_files = [i for i in all_files if os.path.basename(i) != ".DS_Store"]
        all_files_basenames = [os.path.basename(i) for i in all_files]
        img_metadata = pd.DataFrame({
            "img_file": all_files,
            "patient_id": [i.split("-")[1] for i in all_files_basenames],
            "diagnosis": [i.split("-")[0] for i in all_files_basenames],
            "repeat": [i.split("-")[2][:-5] for i in all_files_basenames],
            "train_idx": ["train" in i for i in all_files]
        })
        diagnosis_labels = ['NORMAL', 'BACTERIA', 'VIRUS']
        img_metadata.diagnosis = pd.Categorical(img_metadata.diagnosis, categories=diagnosis_labels)

        train_df = img_metadata.loc[img_metadata.train_idx].reset_index(drop=True)
        test_df = img_metadata.loc[~img_metadata.train_idx].reset_index(drop=True)

        X_train, Y_train = extract_xy(train_df,
                                      resize_transform=resize_transform,
                                      diagnosis_labels=diagnosis_labels)
        X_test, Y_test = extract_xy(test_df,
                                    resize_transform=resize_transform,
                                    diagnosis_labels=diagnosis_labels)

    folds = torch.randint(0, 5, size=(len(X_train),))

    if Y_train.shape[-1] == 1:
        Y_train = torch.concatenate([1 - Y_train, Y_train], dim=-1)
        Y_test = torch.concatenate([1 - Y_test, Y_test], dim=-1)

    if not channels_last:
        permute_dims = (0, -1) + tuple(range(1, X_train.ndim - 1))
        X_train = torch.permute(X_train, dims=permute_dims)
        X_test = torch.permute(X_test, dims=permute_dims)

    return X_train, Y_train, X_test, Y_test, folds


def subsample_dataset(x, y, n_sample):
    idx = []
    for i in range(y.shape[1]):
        idx_i = torch.where(y[:, i] == 1)[0]
        idx_i = idx_i[torch.randperm(len(idx_i))[:n_sample]]
        idx.append(idx_i)
    idx = torch.concatenate(idx)
    x = x[idx]
    y = y[idx]

    return x, y


# </editor-fold>

# <editor-fold desc="Activation Functions">

def mod2(x):
    return x % 2

activation_dict = {"relu": torch.relu,
                   "mod2": mod2,
                   "square": torch.square,
                   }
activation_shift_dict = {"relu": 0,
                         "mod2": 0.5,
                         "square": 0.5,
                         }
activation_rescale_dict = {"relu": 1,
                           "mod2": 1,
                           "square": 1,
                           }


sgd_activations = list(activation_dict.keys())
forward_activations = list(activation_dict.keys())

# </editor-fold>

# <editor-fold desc="Forward mlp training and evaluation functions">

'''Ridge regression function to fit weights'''
def ridge_regression_w(x, y, reg_factor=10, flatten=True, device=device):
    if flatten:
        x = x.reshape((-1, x.shape[-1]))
        y = y.reshape((-1, y.shape[-1]))

    gram_mat = (x.T @ x)
    gram_mat += torch.eye(gram_mat.shape[0], device=device) * reg_factor
    try:
        gram_inv = torch.inverse(gram_mat)
    except:
        gram_inv = torch.eye(gram_mat.shape[0], device=device)
    w_hat = gram_inv @ (x.T @ y)

    if flatten:
        w_hat = torch.unsqueeze(w_hat, dim=0)
    return w_hat


'''
function to fit MLP weight matrix for each layer
'''

def fit_w(x, y, hidden_dim=16,
          flatten=True,
          reg_factor=10.,
          activation="relu",
          return_qu=False,
          device=device,
          training_method="forward_projection",
          ):
    with torch.no_grad():

        if flatten:
            y = y.repeat(repeats=(1, x.shape[1], 1))
            x = x.reshape((-1, x.shape[-1]))
            y = y.reshape((-1, y.shape[-1]))

        q = torch.randn((x.shape[1], hidden_dim), device=device)  # data projection matrix
        u = torch.randn((y.shape[1], hidden_dim), device=device)  # label projection matrix
        y_proj = torch.sign(y @ u)
        match training_method:
            case "forward_projection":
                x_proj = torch.sign(x @ q)
            case "label_projection":
                x_proj = torch.zeros_like(y_proj, device=device)
            case "noisy_label_projection":
                x_proj = torch.sign(torch.randn_like(y_proj, device=device))

        # optional linear transposition
        z = x_proj + y_proj
        z += activation_shift_dict[activation]
        z *= activation_rescale_dict[activation]

        w = ridge_regression_w(x, z,
                               reg_factor=reg_factor,
                               flatten=False,
                               device=device)

        if flatten:
            w = torch.unsqueeze(w, dim=0)

        if return_qu:
            return w, q, u
        else:
            return w, None, None


'''add column of ones to represent intercept'''


def concatenate_ones(x):
    ones_vec = torch.ones_like(x[..., -1, None,])
    x = torch.concatenate([x, ones_vec], dim=-1)
    return x


''' train MLP and return weights and projection matrices'''


def train_forward_mlp(x,
                      y,
                      training_method,
                      activation,
                      hidden_dims=[1000] * 3,
                      reg_factor=10.,
                      return_qu=False,  # returns projection matrices
                      verbose=False,
                      device=device,):
    start_time = time.perf_counter()
    activation_fn = activation_dict[activation]

    w_list = []
    q_list = []
    u_list = []

    x = x.to(device)
    y = y.to(device)

    # fit hidden layers
    for l in range(len(hidden_dims)):

        if verbose:
            print('fitting layer', l)

        # fitting hidden weights
        x = concatenate_ones(x)
        if training_method == "random":
            w = torch.randn((x.shape[-1], hidden_dims[l]), device=device)
            w /= w.norm(dim=-1, keepdim=True)
        if training_method in ["forward_projection", "label_projection", "noisy_label_projection"]:
            w, q, u = fit_w(x, y,
                            hidden_dim=hidden_dims[l],
                            flatten=False,
                            reg_factor=reg_factor,
                            return_qu=return_qu,
                            device=device,
                            activation=activation,
                            training_method=training_method,
                            )
            q_list.append(q)
            u_list.append(u)
        w_list.append(w)

        # forward
        x = activation_fn(x @ w)

    # fitting output layer
    if verbose:
        print('fitting output layer')
    x = concatenate_ones(x)
    w = ridge_regression_w(x, 2 * y - 1, flatten=False, reg_factor=1)
    w_list.append(w)

    end_time = time.perf_counter()
    training_time = end_time - start_time

    return w_list, q_list, u_list, training_time


def evaluate_forward_mlp(x,
                         y,
                         w_list,
                         activation,
                         ):
    activation_fn = activation_dict[activation]

    x = x.to(device)
    y = y.to(device)
    for l in range(len(w_list) - 1):
        x = concatenate_ones(x)
        x = activation_fn(x @ w_list[l])

    x = concatenate_ones(x)
    yhat = x @ w_list[-1]

    test_metrics = compute_metrics(yhat, y)

    return test_metrics


''' evaluate the layer explanation function as a label prediction in each layer'''


def evaluate_explanations_forward_mlp(x,
                                      y,
                                      activation,
                                      w_list,
                                      q_list,
                                      u_list,
                                      ):
    x = x.to(device)
    y = y.to(device)
    activation_fn = activation_dict[activation]

    yhats = []
    for l in range(len(w_list) - 1):
        x = concatenate_ones(x)
        z = x @ w_list[l]
        g_a_q = torch.sign(x @ q_list[l])
        yhat_l = torch.tanh(z - g_a_q) @ torch.linalg.pinv(u_list[l])  # use tanh as a surrogate inverse for sign
        yhats.append(yhat_l)
        x = activation_fn(z)

    x = concatenate_ones(x)
    yhat = x @ w_list[-1]
    yhats.append(yhat)

    test_metrics = [compute_metrics(yhat, y) for yhat in yhats]

    return test_metrics


# </editor-fold>

# <editor-fold desc="Forward conv1d training and evaluation functions (batched)">

'''
function to perform ridge regression over batches of conv1d inputs (channels last)
z refers to z_tilde, the target neural pre-activation potential
'''


def ridge_regression_w_conv1d(x_batches, z_batches, reg_factor=10., device=device):
    x_dim = x_batches[0].shape[-1]
    z_dim = z_batches[1].shape[-1]
    gram_mat = torch.zeros((x_dim, x_dim), device=device)
    xt_z = torch.zeros((x_dim, z_dim), device=device)
    for x_i, z_i in zip(x_batches, z_batches):
        x_i = x_i.to(device)
        z_i = z_i.to(device)
        x_i = x_i.flatten(start_dim=0, end_dim=1)
        z_i = z_i.flatten(start_dim=0, end_dim=1)
        gram_mat += x_i.T @ x_i
        xt_z += x_i.T @ z_i

    # regularise gram matrix
    gram_mat += torch.eye(gram_mat.shape[0], device=device) * reg_factor
    try:
        gram_inv = torch.inverse(gram_mat)
    except:
        print("singular matrix, consider increasing regularisation factor")
        gram_inv = torch.eye(gram_mat.shape[0], device=device)
    w_hat = gram_inv @ xt_z

    return w_hat


'''
function to fit convolutional weights. Channels last
'''


def fit_w_conv1d(x_batches,
                 y_batches,
                 hidden_dim=32,
                 reg_factor=10.,
                 return_qu=False,
                 activation="relu",
                 device=device,
                 training_method="forward_projection",):
    x_channels = x_batches[0].shape[-1]
    y_channels = y_batches[0].shape[-1]

    q = torch.randn((x_channels, hidden_dim), device=device)  # data projection matrix
    u = torch.randn((y_channels, hidden_dim), device=device)  # label projection matrix
    z_batches = []  # batches of targets
    for x_i, y_i in zip(x_batches, y_batches):

        x_i = x_i.to(device)
        y_i = y_i.to(device)

        # project labels
        y_proj = torch.sign(y_i @ u)
        match training_method:
            case "forward_projection":
                x_proj = torch.sign(x_i @ q)
            case "label_projection":
                x_proj = torch.zeros(x_i.shape[:-1] + (u.shape[-1],),
                                     device=device)
            case "noisy_label_projection":
                x_proj = torch.sign(torch.randn(x_i.shape[:-1] + (u.shape[-1],),
                                                device=device))

        # generate target potentials (z)
        z_i = x_proj + y_proj

        # transpose distribution of labels
        if activation_shift_dict[activation] != 0:
            z_i += activation_shift_dict[activation]
        if activation_rescale_dict[activation] != 1:
            z_i *= activation_rescale_dict[activation]
        z_batches.append(z_i.to("cpu"))

    # model target potentials
    w = ridge_regression_w_conv1d(x_batches, z_batches, reg_factor=reg_factor)

    if return_qu:
        return w, q, u
    else:
        return w, None, None


'''
function to fit conv1d neural network (channels last)
convolutional pyramid neural network
'''


def train_forward_conv1d(x,
                         y,
                         training_method,
                         activation='relu',
                         hidden_dim=32,
                         n_blocks=4,
                         kernel_size=3,
                         batch_size=100,
                         return_qu=False,
                         verbose=False,
                         device=device,
                         ):
    with torch.no_grad():

        activation_fn = activation_dict[activation]

        if y.ndim == 2:
            y = torch.unsqueeze(y, dim=1)

        # define hidden layer dimensions for convolutional pyramid
        hidden_dims = [round(hidden_dim * 2 ** (i // 2)) for i in range(n_blocks * 2)]

        start_time = time.perf_counter()
        w_list = []
        q_list = []
        u_list = []

        rand_idx = torch.randperm(len(x))
        x_batches = list(torch.split(x[rand_idx], split_size_or_sections=batch_size))
        y_batches = list(torch.split(y[rand_idx], split_size_or_sections=batch_size))

        # fit hidden layers
        for l in range(len(hidden_dims)):

            if verbose:
                print('fitting layer', l)

            # pooling
            step_size = 2 - ((l + 1) % 2)

            # convolution
            for i in range(len(x_batches)):
                x_i = x_batches[i]
                x_i = x_i.unfold(dimension=1, size=kernel_size, step=step_size).flatten(start_dim=2)
                x_i = concatenate_ones(x_i)
                x_batches[i] = x_i

            # fitting hidden weights
            if training_method == "random":
                w = torch.randn((x_batches[0].shape[-1], hidden_dims[l]), device=device)
                w /= w.norm(dim=-1, keepdim=True)
            if training_method in ["forward_projection", "label_projection", "noisy_label_projection"]:
                w, q, u = fit_w_conv1d(x_batches,
                                       y_batches,
                                       hidden_dim=hidden_dims[l],
                                       activation=activation,
                                       training_method=training_method,
                                       return_qu=return_qu,
                                       )
                q_list.append(q)
                u_list.append(u)
            w_list.append(w)

            # forward pass
            x_batches = [activation_fn(x_i.to(device) @ w).to("cpu") for x_i in x_batches]

        # fitting output layer
        if verbose:
            print('fitting output layer')
        for i in range(len(x_batches)):
            x_batches[i] = concatenate_ones(x_batches[i])
            x_batches[i] = torch.mean(x_batches[i], dim=1, keepdim=True)
            y_batches[i] = 2 * y_batches[i] - 1

        # fit output layer weights
        w = ridge_regression_w_conv1d(x_batches, y_batches, reg_factor=1)  # 1

        w_list.append(w)
        end_time = time.perf_counter()
        training_time = end_time - start_time

        return w_list, q_list, u_list, training_time


def evaluate_forward_conv1d(x,
                            y,
                            w_list,
                            activation,
                            kernel_size=3,
                            batch_size=1000
                            ):
    activation_fn = activation_dict[activation]
    x_batches = torch.split(x, split_size_or_sections=batch_size)

    yhat = []
    for x_i in x_batches:
        x_i = x_i.to(device)

        for l in range(len(w_list) - 1):
            # convolution and pooling
            stride = 2 - ((l + 1) % 2)
            x_i = x_i.unfold(dimension=1, size=kernel_size, step=stride).flatten(start_dim=2)
            x_i = concatenate_ones(x_i)

            # forward
            x_i = activation_fn(x_i @ w_list[l])

        # output
        x_i = concatenate_ones(x_i)
        y = torch.squeeze(y)
        x_i = torch.mean(x_i, dim=1)
        yhat_i = x_i @ w_list[-1]
        yhat.append(yhat_i.to("cpu"))

    yhat = torch.concatenate(yhat)

    metrics = compute_metrics(yhat, y)

    return metrics


# </editor-fold>

# <editor-fold desc="Forward conv2d training and evaluation functions (batched)">

'''
weights over conv2d data batches. Channels last. 
z refers to the target potentials
'''
def ridge_regression_w_conv2d(x_batches, z_batches, reg_factor=10., device=device):
    x_dim = x_batches[0].shape[-1] # data
    z_dim = z_batches[1].shape[-1] # targets

    #accumulate data gram matrix and cross product of data and targets
    gram_mat = torch.zeros((x_dim, x_dim), device=device)
    xt_z = torch.zeros((x_dim, z_dim), device=device)
    for x_i, z_i in zip(x_batches, z_batches):
        x_i = x_i.to(device)
        z_i = z_i.to(device)
        x_i = x_i.flatten(start_dim=0, end_dim=2)
        z_i = z_i.flatten(start_dim=0, end_dim=2)
        xt_z += x_i.T @ z_i
        gram_mat += x_i.T @ x_i

    #regularise
    gram_mat += torch.eye(gram_mat.shape[0], device=device) * reg_factor

    #invert gram matrix
    try:
        gram_inv = torch.inverse(gram_mat)
    except:
        print("singular gram matrix, consider increasing regularisation factor")
        gram_inv = torch.eye(gram_mat.shape[0], device=device)

    #compute weight matrix
    w_hat = gram_inv @ xt_z

    return w_hat

'''
function to fit 2d convolutional layer weights over data batches
channels last

'''

def fit_w_conv2d(x_batches,
                 y_batches,
                 hidden_dim=16,
                 reg_factor=0.01,
                 return_qu=False,
                 activation="relu",
                 device=device,
                 training_method="forward_projection"):
    x_channels = x_batches[0].shape[-1]
    y_channels = y_batches[0].shape[-1]

    q = torch.randn((x_channels, hidden_dim), device=device) # data projection matrix
    u = torch.randn((y_channels, hidden_dim), device=device) # label projection matx
    z_batches = [] # targets
    for x_i, y_i in zip(x_batches, y_batches):

        x_i = x_i.to(device)
        y_i = y_i.to(device)

        #generate target values (z)
        y_proj = torch.sign(y_i @ u)
        match training_method:
            case "forward_projection":
                x_proj = torch.sign(x_i @ q)
            case "label_projection":
                x_proj = torch.zeros(x_i.shape[:-1] + (u.shape[-1],),
                                     device=device)
            case "noisy_label_projection":
                x_proj = torch.sign(torch.randn(x_i.shape[:-1] + (u.shape[-1],),
                                                device=device))

        z_i = x_proj + y_proj

        # transpose target distribution
        if activation_shift_dict[activation] != 0:
            z_i += activation_shift_dict[activation]
        if activation_rescale_dict[activation] != 1:
            z_i *= activation_rescale_dict[activation]
        z_batches.append(z_i.to("cpu"))

    #fit weight
    w = ridge_regression_w_conv2d(x_batches, z_batches, reg_factor=reg_factor)

    if return_qu:
        return w, q, u
    else:
        return w, None, None


def train_forward_conv2d(x,
                         y,
                         training_method,
                         activation='relu',
                         hidden_dim=16,
                         n_blocks=3,
                         kernel_size=3,
                         batch_size=100,
                         reg_factor=0.01,
                         return_qu=False,
                         verbose=False,
                         device=device,
                         ):
    activation_fn = activation_dict[activation]

    if y.ndim == 2:
        y = y[:, None, None, :]

    hidden_dims = [round(hidden_dim * 2 ** (i // 2)) for i in range(n_blocks * 2)]

    start_time = time.perf_counter()
    w_list = [] # layer weight matrices
    q_list = [] # data projection matrices
    u_list = [] # label projeciton matrices

    rand_idx = torch.randperm(len(x))
    x_batches = list(torch.split(x[rand_idx], split_size_or_sections=batch_size))
    y_batches = list(torch.split(y[rand_idx], split_size_or_sections=batch_size))

    # fit hidden layers
    for l in range(len(hidden_dims)):

        if verbose:
            print('fitting layer', l)

        # pooling
        stride = 2 - ((l + 1) % 2)

        # convolution
        for i in range(len(x_batches)):
            x_i = x_batches[i]
            x_i = x_i.unfold(dimension=1, size=kernel_size, step=stride)  #
            x_i = x_i.unfold(dimension=2, size=kernel_size, step=stride)  #
            x_i = x_i.flatten(start_dim=3)
            x_i = concatenate_ones(x_i)
            x_batches[i] = x_i

        # fitting hidden weights
        if training_method == "random":
            w = torch.randn((x_batches[0].shape[-1], hidden_dims[l])).to(device)
            w /= w.norm(dim=-1, keepdim=True)
        if training_method in ["forward_projection", "label_projection", "noisy_label_projection"]:
            w, q, u = fit_w_conv2d(x_batches,
                                   y_batches,
                                   hidden_dim=hidden_dims[l],
                                   return_qu=return_qu,
                                   activation=activation,
                                   training_method=training_method,
                                   reg_factor=reg_factor)
            q_list.append(q)
            u_list.append(u)
        w_list.append(w)

        # forward
        x_batches = [activation_fn(x_i.to(device) @ w).to("cpu") for x_i in x_batches]

    # fitting output layer
    if verbose:
        print('fitting output layer')
    for i in range(len(x_batches)):
        x_batches[i] = concatenate_ones(x_batches[i])
        x_batches[i] = torch.mean(x_batches[i], dim=(1, 2), keepdim=True)
        y_batches[i] = 2 * y_batches[i] - 1

    # fit weight
    w = ridge_regression_w_conv2d(x_batches, y_batches, reg_factor=1)

    w_list.append(w)
    end_time = time.perf_counter()
    training_time = end_time - start_time

    return w_list, q_list, u_list, training_time


def evaluate_forward_conv2d(x,
                            y,
                            w_list,
                            activation,
                            kernel_size=3,
                            batch_size=1000
                            ):
    activation_fn = activation_dict[activation]
    x_batches = torch.split(x, split_size_or_sections=batch_size)

    yhat = []
    for x_i in x_batches:
        x_i = x_i.to(device)

        for l in range(len(w_list) - 1):

            # convolution and pooling
            stride = 2 - ((l + 1) % 2)
            x_i = x_i.unfold(dimension=1, size=kernel_size, step=stride)  #
            x_i = x_i.unfold(dimension=2, size=kernel_size, step=stride)  #
            x_i = x_i.flatten(start_dim=3)
            x_i = concatenate_ones(x_i)

            # forward
            x_i = activation_fn(x_i @ w_list[l])

        # output
        x_i = concatenate_ones(x_i)
        y = torch.squeeze(y)

        # extract global average as prediction
        x_i = torch.mean(x_i, dim=(1, 2))
        yhat_i = x_i @ w_list[-1]
        yhat.append(yhat_i.to("cpu"))

    yhat = torch.concatenate(yhat)

    metrics = compute_metrics(yhat, y)

    return metrics



# </editor-fold>

# <editor-fold desc="Forward mlp experiments">

model_parameters = expand_grid({
    'fold': list(range(5)),
    'training_method': ["forward_projection", "random", "label_projection", "noisy_label_projection"],
    'activation': forward_activations,
})

tabular_datasets = ["FashionMNIST"]
verbose = False

#set seed
seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
forward_mlp_experiments = []
for dataset_i in tabular_datasets:

    print(dataset_i)
    X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i)

    for model_parameters_i in range(len(model_parameters)):
        print(model_parameters_i)

        training_method = model_parameters.training_method[model_parameters_i]
        activation = model_parameters.activation[model_parameters_i]
        fold = model_parameters.fold[model_parameters_i]

        if False:
            training_method="forward_projection"
            activation="relu"
            fold=0
            verbose=True

        train_folds = folds != fold
        val_folds = torch.logical_not(train_folds)
        X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
        Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

        w_list, _, _, training_time = train_forward_mlp(x=X_train,
                                                        y=Y_train,
                                                        training_method=training_method,
                                                        activation=activation
                                                        )
        train_metrics = evaluate_forward_mlp(x=X_train,
                                             y=Y_train,
                                             w_list=w_list,
                                             activation=activation,
                                             )

        val_metrics = evaluate_forward_mlp(x=X_val,
                                           y=Y_val,
                                           w_list=w_list,
                                           activation=activation,
                                           )

        test_metrics = evaluate_forward_mlp(x=X_test,
                                            y=Y_test,
                                            w_list=w_list,
                                            activation=activation,
                                            )
        if verbose:
            print(training_method)
            print(activation)
            print(train_metrics)
            print(val_metrics)
            print(test_metrics)

        out = {
            'dataset': dataset_i,
            'training_method': training_method,
            'fold': fold,
            'activation': activation,
            'train_auc': train_metrics[0].item(),
            'train_acc': train_metrics[1].item(),
            'train_prec': train_metrics[2].item(),
            'train_recall': train_metrics[3].item(),
            'train_f1': train_metrics[4].item(),
            'val_auc': val_metrics[0].item(),
            'val_acc': val_metrics[1].item(),
            'val_prec': val_metrics[2].item(),
            'val_recall': val_metrics[3].item(),
            'val_f1': val_metrics[4].item(),
            'test_auc': test_metrics[0].item(),
            'test_acc': test_metrics[1].item(),
            'test_prec': test_metrics[2].item(),
            'test_recall': test_metrics[3].item(),
            'test_f1': test_metrics[4].item(),
            'training_time': training_time,
            "training_epochs": 1,
        }
        forward_mlp_experiments.append(out)

forward_mlp_experiments = pd.DataFrame(forward_mlp_experiments)
output_file = os.path.join(output_dir, "forward_mlp_experiments.csv")
forward_mlp_experiments.to_csv(path_or_buf=output_file)


# </editor-fold>

# <editor-fold desc="Forward conv1d experiments">

model_parameters = expand_grid({

    'fold': list(range(5)),
    'training_method': ["forward_projection", "random", "label_projection", "noisy_label_projection"],
    'activation': forward_activations,
})
conv1d_datasets = ['ptbxl_mi', "human_nontata_promoters"]
verbose = True

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
forward_conv1d_experiments = []
for dataset_i in conv1d_datasets:

    print(dataset_i)
    X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i)

    for model_parameters_i in range(len(model_parameters)):

        print(model_parameters_i)

        training_method = model_parameters.training_method[model_parameters_i]
        fold = model_parameters.fold[model_parameters_i]
        activation = model_parameters.activation[model_parameters_i]
        hidden_dim = 32
        n_blocks = 4

        # train 1d conv
        train_folds = folds != fold
        val_folds = torch.logical_not(train_folds)
        X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
        Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

        w_list, _, _, training_time = train_forward_conv1d(x=X_train,
                                                           y=Y_train,
                                                           training_method=training_method,
                                                           hidden_dim=hidden_dim,
                                                           activation=activation,
                                                           n_blocks=n_blocks,
                                                           device=device,
                                                           batch_size=1000
                                                           )
        train_metrics = evaluate_forward_conv1d(x=X_train,
                                                y=Y_train,
                                                w_list=w_list,
                                                activation=activation)
        val_metrics = evaluate_forward_conv1d(x=X_val,
                                              y=Y_val,
                                              w_list=w_list,
                                              activation=activation)
        test_metrics = evaluate_forward_conv1d(x=X_test,
                                               y=Y_test,
                                               w_list=w_list,
                                               activation=activation)
        if verbose:
            print(training_method)
            print(train_metrics)
            print(val_metrics)
            print(test_metrics)

        out = {
            'dataset': dataset_i,
            'training_method': training_method,
            'fold': fold,
            'activation': activation,
            'hidden_dim': hidden_dim,
            'n_blocks': n_blocks,
            'train_auc': train_metrics[0].item(),
            'train_acc': train_metrics[1].item(),
            'train_prec': train_metrics[2].item(),
            'train_recall': train_metrics[3].item(),
            'train_f1': train_metrics[4].item(),
            'val_auc': val_metrics[0].item(),
            'val_acc': val_metrics[1].item(),
            'val_prec': val_metrics[2].item(),
            'val_recall': val_metrics[3].item(),
            'val_f1': val_metrics[4].item(),
            'test_auc': test_metrics[0].item(),
            'test_acc': test_metrics[1].item(),
            'test_prec': test_metrics[2].item(),
            'test_recall': test_metrics[3].item(),
            'test_f1': test_metrics[4].item(),
            'training_time': training_time,
        }
        forward_conv1d_experiments.append(out)
forward_conv1d_experiments = pd.DataFrame(forward_conv1d_experiments)
output_file = os.path.join(output_dir, "forward_conv1d_experiments.csv")
forward_conv1d_experiments.to_csv(path_or_buf=output_file)


# </editor-fold>

# <editor-fold desc="SGD mlp training and evaluation functions">

class mlpModel(nn.Module):
    def __init__(self,
                 training_method,
                 activation_fn,
                 in_features=None,
                 hidden_dims=None,
                 num_classes=None,
                 ):
        super(mlpModel, self).__init__()
        self.activation_fn = activation_fn
        self.in_features = [in_features] + hidden_dims
        if training_method == "forward_forward":
            self.in_features[0] += num_classes
        self.out_features = hidden_dims + [num_classes]
        self.layers = nn.ModuleList(
            [nn.Linear(in_l, out_l) for in_l, out_l in zip(self.in_features, self.out_features)])
        self.training_method = training_method
        self.detach_output = training_method != "backprop"
        if training_method == "backprop":
            self.opt = torch.optim.Adam(self.layers.parameters(), )
        if training_method in ["local_supervision"]:
            self.opts = [torch.optim.Adam(layer_l.parameters(), ) for layer_l in self.layers]
        if training_method == "forward_forward":
            self.opts = [torch.optim.Adam(layer_l.parameters(),
                                          lr=0.03) for layer_l in self.layers]
        if training_method == "local_supervision":
            self.ls_layers = nn.ModuleList([nn.Linear(out_l, num_classes) for out_l in hidden_dims])

    def forward(self, x):
        for layer_l in self.layers[:-1]:
            x = layer_l(x)
            x = self.activation_fn(x)
        if self.detach_output:
            x = torch.detach(x)
        x = self.layers[-1](x)
        return x

    def forward_ls(self, x):
        yhats = []
        for layer_l, ls_layer_l in zip(self.layers[:-1], self.ls_layers):
            x = layer_l(x)
            x = self.activation_fn(x)
            yhat_l = ls_layer_l(x)
            yhats.append(yhat_l)
            x = torch.detach(x)
        yhats.append(self.layers[-1](x))
        return yhats

    def forward_ff(self, xy):
        goodnesses = []
        for layer_l in self.layers[:-1]:
            xy = xy / (xy.norm(dim=1, keepdim=True) + 0.001)
            xy = layer_l(xy)
            xy = self.activation_fn(xy)
            goodness_l = xy.square().mean(dim=1)
            goodnesses.append(goodness_l)
            xy = torch.detach(xy)
        return goodnesses


def train_sgd(model,
              x,
              y,
              loss_fn,
              batch_size=10):
    torch.cuda.empty_cache()
    model.train()

    # training
    rand_idx = torch.randperm(len(x))
    x_batches = torch.split(x[rand_idx], split_size_or_sections=batch_size)
    y_batches = torch.split(y[rand_idx], split_size_or_sections=batch_size)
    train_loss = 0
    if model.training_method == "backprop":
        for x_i, y_i in zip(x_batches, y_batches):
            x_i = x_i.to(device)
            y_i = y_i.to(device)
            yhat_i = model(x_i)
            loss = loss_fn(yhat_i, y_i)
            model.opt.zero_grad()
            loss.backward()
            model.opt.step()
            train_loss += loss
    if model.training_method == "local_supervision":
        for x_i, y_i in zip(x_batches, y_batches):
            x_i = x_i.to(device)
            y_i = y_i.to(device)
            yhats = model.forward_ls(x_i)
            for l in range(len(yhats)):
                loss_l = loss_fn(yhats[l], y_i)
                model.opts[l].zero_grad()
                loss_l.backward(inputs=tuple(model.layers[l].parameters()))
                model.opts[l].step()
            train_loss += loss_l / len(yhats)
    if model.training_method == "forward_forward":
        for x_i, y_i in zip(x_batches, y_batches):
            x_i = x_i.to(device)
            y_i = y_i.to(device)
            y_neg_i = torch.argmax(torch.rand_like(y_i) - y_i, dim=1).to(device)
            y_neg_i = torch.eye(y_i.shape[1]).to(device)[y_neg_i]
            while y_i.ndim < x_i.ndim:
                y_i = torch.unsqueeze(y_i, dim=-1)
                y_neg_i = torch.unsqueeze(y_neg_i, dim=-1)
            y_i = y_i.repeat(repeats=(1, 1) + x_i.shape[2:])
            y_neg_i = y_neg_i.repeat(repeats=(1, 1) + x_i.shape[2:])
            xy_pos = torch.concatenate([x_i, y_i], dim=1)
            xy_neg = torch.concatenate([x_i, y_neg_i], dim=1)
            g_pos = model.forward_ff(xy_pos)
            g_neg = model.forward_ff(xy_neg)
            for l in range(len(g_pos)):
                loss_l = torch.log(1 + torch.exp(torch.concatenate([2 - g_pos[l], g_neg[l] - 2]))).mean()
                model.opts[l].zero_grad()
                loss_l.backward(inputs=tuple(model.layers[l].parameters()))
                model.opts[l].step()
                train_loss += loss_l / len(x_batches)
    train_loss /= len(x_batches)

    return train_loss


def validate_sgd(model,
                 x,
                 y,
                 loss_fn,
                 batch_size=25, ):
    torch.cuda.empty_cache()
    model.eval()
    with torch.no_grad():
        val_loss = 0
        x_batches = torch.split(x, split_size_or_sections=batch_size)
        y_batches = torch.split(y, split_size_or_sections=batch_size)
        if model.training_method in ["backprop", "local_supervision"]:
            for x_i, y_i in zip(x_batches, y_batches):
                x_i = x_i.to(device)
                y_i = y_i.to(device)
                yhat_i = model(x_i)
                loss_i = loss_fn(yhat_i, y_i)
                val_loss += loss_i
        if model.training_method == "forward_forward":
            for x_i, y_i in zip(x_batches, y_batches):
                x_i = x_i.to(device)
                y_i = y_i.to(device)
                y_neg_i = torch.argmax(torch.rand_like(y_i) - y_i, dim=1).to(device)
                y_neg_i = torch.eye(y_i.shape[1]).to(device)[y_neg_i]
                while y_i.ndim < x_i.ndim:
                    y_i = torch.unsqueeze(y_i, dim=-1)
                    y_neg_i = torch.unsqueeze(y_neg_i, dim=-1)
                y_i = y_i.repeat(repeats=(1, 1) + x_i.shape[2:])
                y_neg_i = y_neg_i.repeat(repeats=(1, 1) + x_i.shape[2:])
                xy_pos = torch.concatenate([x_i, y_i], dim=1)
                xy_neg = torch.concatenate([x_i, y_neg_i], dim=1)
                g_pos = model.forward_ff(xy_pos)
                g_neg = model.forward_ff(xy_neg)
                for g_pos_l, g_neg_l in zip(g_pos, g_neg):
                    loss_l = torch.log(1 + torch.exp(torch.concatenate([2 - g_pos_l, g_neg_l - 2]))).mean()
                    val_loss += loss_l / len(g_pos)
        val_loss /= len(x_batches)
        return val_loss


def evaluate_sgd(model,
                 x,
                 y,
                 batch_size=25,
                 ):
    model.eval()
    with torch.no_grad():
        torch.cuda.empty_cache()
        x_batches = torch.split(x, split_size_or_sections=batch_size)
        if model.training_method in ["backprop", "local_supervision"]:
            yhat = [model(x_i.to(device)) for x_i in x_batches]
        if model.training_method == "forward_forward":
            yhat = []
            n_classes = y.shape[1]
            for x_i in x_batches:
                x_i = x_i.to(device)
                y_candidates = torch.eye(n_classes).unsqueeze(1).repeat(1, len(x_i), 1).to(device)
                while y_candidates.ndim < (x_i.ndim + 1):
                    y_candidates = torch.unsqueeze(y_candidates, dim=-1)
                y_candidates = y_candidates.repeat(repeats=(1, 1, 1) + x_i.shape[2:])
                yhat_i = torch.zeros((len(x_i), n_classes))
                for j in range(n_classes):
                    xy_ij = torch.concatenate([x_i, y_candidates[j]], dim=1)
                    goodness_i = model.forward_ff(xy_ij)
                    yhat_i[:, j] = torch.mean(torch.stack(goodness_i), dim=0)
                yhat.append(yhat_i)

        yhat = torch.concatenate(yhat)
        metrics = compute_metrics(yhat, y)
        return metrics


def train_sgd_mlp(X_train,
                  Y_train,
                  X_val,
                  Y_val,
                  activation,
                  training_method,
                  hidden_dims=[1000] * 3,
                  patience=5,
                  max_epochs=100,
                  batch_size=50,
                  verbose=False,
                  loss_fn=torch.nn.CrossEntropyLoss()):
    torch.cuda.empty_cache()
    start_time = time.perf_counter()
    activation_fn = activation_dict[activation]

    in_features = X_train.shape[1]
    model = mlpModel(
        training_method=training_method,
        in_features=in_features,
        hidden_dims=hidden_dims,
        num_classes=Y_train.shape[1],
        activation_fn=activation_fn,
    ).to(device)
    train_loss = []
    val_loss = []
    best_val_loss = torch.inf
    patience_counter = 0
    for epoch_i in range(max_epochs):
        train_loss_i = train_sgd(model=model,
                                 x=X_train,
                                 y=Y_train,
                                 loss_fn=loss_fn,
                                 batch_size=batch_size)
        train_loss.append(train_loss_i.item())
        val_loss_i = validate_sgd(model=model,
                                  x=X_val,
                                  y=Y_val,
                                  loss_fn=loss_fn,
                                  batch_size=batch_size)
        val_loss.append(val_loss_i.item())
        if verbose:
            print(val_loss_i)
        if val_loss_i < best_val_loss:
            best_val_loss = val_loss_i
            patience_counter = 0
        else:
            patience_counter += 1
        if patience_counter == (patience - 1):
            break

    end_time = time.perf_counter()
    training_time = end_time - start_time
    training_epochs = epoch_i

    return model, training_time, training_epochs


# </editor-fold>

# <editor-fold desc="SGD conv1d training and evaluation functions">

class conv1dModel(nn.Module):
    def __init__(self,
                 training_method,
                 activation_fn,
                 in_features=None,
                 hidden_dims=None,
                 num_classes=None,
                 kernel_size=3,
                 ):
        super(conv1dModel, self).__init__()
        self.activation_fn = activation_fn
        self.in_features = [in_features] + hidden_dims
        if training_method == "forward_forward":
            self.in_features[0] += num_classes
        self.out_features = hidden_dims + [num_classes]
        self.layers = []
        for in_l, out_l in zip(self.in_features[:-1], self.out_features[:-1]):
            self.layers.append(nn.Conv1d(in_l, out_l, kernel_size))
        self.layers.append(nn.Linear(self.in_features[-1], self.out_features[-1]))
        self.layers = nn.ModuleList(self.layers)
        self.batch_norms = nn.ModuleList([nn.BatchNorm1d(out_l) for out_l in hidden_dims[1::2]])
        self.training_method = training_method
        if training_method == "backprop":
            self.opt = torch.optim.Adam(self.layers.parameters())
        if training_method == "local_supervision":
            self.ls_layers = nn.ModuleList(
                [nn.Linear(out_l, num_classes) for out_l in hidden_dims])
            self.opts = [torch.optim.Adam(layer_l.parameters()) for layer_l in self.layers]
        if training_method == "forward_forward":
            self.opts = [torch.optim.Adam(layer_l.parameters(),
                                          lr=0.03) for layer_l in self.layers]

    def forward(self, x):
        for l in range(len(self.layers) - 1):
            x = self.layers[l](x)
            x = self.activation_fn(x)
            if l % 2:
                x = x[..., ::2]
                if l < len(self.batch_norms):
                    x = self.batch_norms[l // 2](x)
        x = torch.mean(x, dim=2)
        yhat = self.layers[-1](x)
        return yhat

    def forward_ls(self, x):
        yhats = []
        for l in range(len(self.layers) - 1):
            x = self.layers[l](x)
            x = self.activation_fn(x)
            x_mu = torch.mean(x, dim=2)
            yhat_l = self.ls_layers[l](x_mu)
            yhats.append(yhat_l)
            if l % 2:
                x = x[..., ::2]
                if l < len(self.batch_norms):
                    x = self.batch_norms[l // 2](x)
            x = torch.detach(x)
        x = torch.mean(x, dim=2)
        yhat = self.layers[-1](x)
        yhats.append(yhat)
        return yhats

    def forward_ff(self, xy):
        goodnesses = []
        for l in range(len(self.layers) - 1):
            xy = xy / (xy.norm(dim=1, keepdim=True) + 0.001)
            xy = self.layers[l](xy)
            xy = self.activation_fn(xy)
            goodness_l = xy.square().mean(dim=(1, 2))
            goodnesses.append(goodness_l)
            if l % 2:
                xy = xy[..., ::2]
                if l < len(self.batch_norms):
                    xy = self.batch_norms[l // 2](xy)
            xy = torch.detach(xy)
        return goodnesses


def train_sgd_conv1d(X_train,
                     Y_train,
                     X_val,
                     Y_val,
                     hidden_dims,
                     activation,
                     training_method,
                     kernel_size=3,
                     patience=5,
                     max_epochs=50,
                     batch_size=25,
                     verbose=False,
                     loss_fn=torch.nn.CrossEntropyLoss()):
    torch.cuda.empty_cache()
    start_time = time.perf_counter()

    activation_fn = activation_dict[activation]
    model = conv1dModel(
        in_features=X_train.shape[1],
        hidden_dims=hidden_dims,
        num_classes=Y_train.shape[1],
        activation_fn=activation_fn,
        kernel_size=kernel_size,
        training_method=training_method
    ).to(device)
    train_loss = []
    val_loss = []
    best_val_loss = torch.inf
    patience_counter = 0
    for epoch_i in range(max_epochs):
        train_loss_i = train_sgd(model=model,
                                 x=X_train,
                                 y=Y_train,
                                 loss_fn=loss_fn,
                                 batch_size=batch_size
                                 )
        train_loss.append(train_loss_i.item())
        val_loss_i = validate_sgd(model=model,
                                  x=X_val,
                                  y=Y_val,
                                  loss_fn=loss_fn,
                                  batch_size=batch_size)
        val_loss.append(val_loss_i.item())
        if verbose:
            print(val_loss_i)
        if val_loss_i < best_val_loss:
            best_val_loss = val_loss_i
            patience_counter = 0
        else:
            patience_counter += 1
        if patience_counter == (patience - 1):
            break

    end_time = time.perf_counter()
    training_time = end_time - start_time
    training_epochs = epoch_i

    model = conv1dModel(
        in_features=X_train.shape[1],
        hidden_dims=hidden_dims,
        num_classes=Y_train.shape[1],
        activation_fn=activation_fn,
        kernel_size=kernel_size,
        training_method=training_method
    ).to(device)
    print("final training")
    X_trainval = torch.concatenate([X_train, X_val])
    Y_trainval = torch.concatenate([Y_train, Y_val])
    for _ in range(epoch_i):
        _ = train_sgd(model=model,
                      x=X_trainval,
                      y=Y_trainval,
                      loss_fn=loss_fn,
                      batch_size=batch_size)

    return model, training_time, training_epochs


# </editor-fold>

# <editor-fold desc="SGD conv2d training and evaluation functions">

class conv2dModel(nn.Module):
    def __init__(self,
                 training_method,
                 activation_fn,
                 in_features=None,
                 hidden_dims=None,
                 num_classes=None,
                 kernel_size=3,
                 lr=0.001
                 ):
        super().__init__()
        self.activation_fn = activation_fn
        self.in_features = [in_features] + hidden_dims
        if training_method == "forward_forward":
            self.in_features[0] += num_classes
        self.out_features = hidden_dims + [num_classes]
        self.layers = []
        for in_l, out_l in zip(self.in_features[:-1], self.out_features[:-1]):
            self.layers.append(nn.Conv2d(in_l, out_l, kernel_size))
        self.layers.append(nn.Linear(self.in_features[-1], self.out_features[-1]))
        self.layers = nn.ModuleList(self.layers)
        self.batch_norms = nn.ModuleList([nn.BatchNorm2d(out_l) for out_l in hidden_dims[1::2]])
        self.training_method = training_method
        if training_method == "backprop":
            self.opt = torch.optim.Adam(self.layers.parameters(), lr=lr)
        if training_method == "local_supervision":
            self.ls_layers = nn.ModuleList(
                [nn.Linear(out_l, num_classes) for out_l in hidden_dims])
            self.opts = [torch.optim.Adam(layer_l.parameters(), lr=lr) for layer_l in self.layers]
        if training_method == "forward_forward":
            self.opts = [torch.optim.Adam(layer_l.parameters(),
                                          lr=lr) for layer_l in self.layers]

    def forward(self, x):
        for l in range(len(self.layers) - 1):
            x = self.layers[l](x)
            x = self.activation_fn(x)
            if l % 2:
                x = x[..., ::2, ::2]
                if l < len(self.batch_norms):
                    x = self.batch_norms[l // 2](x)
        x = torch.mean(x, dim=(2, 3))
        yhat = self.layers[-1](x)
        return yhat

    def forward_ls(self, x):
        yhats = []
        for l in range(len(self.layers) - 1):
            x = self.layers[l](x)
            x = self.activation_fn(x)
            x_mu = torch.mean(x, dim=(2, 3))
            yhat_l = self.ls_layers[l](x_mu)
            yhats.append(yhat_l)
            if l % 2:
                x = x[..., ::2, ::2]
                if l < len(self.batch_norms):
                    x = self.batch_norms[l // 2](x)
            x = torch.detach(x)
        x = torch.mean(x, dim=(2, 3))
        yhat = self.layers[-1](x)
        yhats.append(yhat)
        return yhats

    def forward_ff(self, xy):
        goodnesses = []
        for l in range(len(self.layers) - 1):
            xy = xy / (xy.norm(dim=1, keepdim=True) + 0.001)
            xy = self.layers[l](xy)
            xy = self.activation_fn(xy)
            goodness_l = xy.square().mean(dim=(1, 2, 3))
            goodnesses.append(goodness_l)
            if l % 2:
                xy = xy[..., ::2, ::2]
                if l < len(self.batch_norms):
                    xy = self.batch_norms[l // 2](xy)
            xy = torch.detach(xy)
        return goodnesses


def train_sgd_conv2d(X_train,
                     Y_train,
                     X_val,
                     Y_val,
                     hidden_dims,
                     activation,
                     training_method,
                     kernel_size=3,
                     patience=5,
                     max_epochs=50,
                     batch_size=5,
                     verbose=False,
                     loss_fn=torch.nn.CrossEntropyLoss(),
                     lr=0.001
                     ):
    torch.cuda.empty_cache()
    start_time = time.perf_counter()

    activation_fn = activation_dict[activation]
    model = conv2dModel(
        in_features=X_train.shape[1],
        hidden_dims=hidden_dims,
        num_classes=Y_train.shape[1],
        activation_fn=activation_fn,
        kernel_size=kernel_size,
        training_method=training_method,
        lr=lr
    ).to(device)
    train_loss = []
    val_loss = []
    best_val_loss = torch.inf
    patience_counter = 0
    for epoch_i in range(max_epochs):
        train_loss_i = train_sgd(model=model,
                                 x=X_train,
                                 y=Y_train,
                                 loss_fn=loss_fn,
                                 batch_size=batch_size
                                 )
        train_loss.append(train_loss_i.item())
        val_loss_i = validate_sgd(model=model,
                                  x=X_val,
                                  y=Y_val,
                                  loss_fn=loss_fn,
                                  batch_size=batch_size)
        val_loss.append(val_loss_i.item())
        if verbose:
            print(val_loss_i)
        if val_loss_i < best_val_loss:
            best_val_loss = val_loss_i
            patience_counter = 0
        else:
            patience_counter += 1
        if patience_counter == (patience - 1):
            break

    end_time = time.perf_counter()
    training_time = end_time - start_time
    training_epochs = epoch_i

    return model, training_time, training_epochs


# </editor-fold>

# <editor-fold desc="SGD mlp experiments">

model_parameters = expand_grid({
    'fold': list(range(5)),
    'training_method': ["backprop", "local_supervision", "forward_forward"],
    'activation': sgd_activations,
})

tabular_datasets = ["FashionMNIST"]

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
sgd_mlp_experiments = []
for dataset_i in tabular_datasets:

    print(dataset_i)
    X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i)

    for model_parameters_i in range(len(model_parameters)):

        print(model_parameters_i)
        fold = model_parameters.fold[model_parameters_i]
        training_method = model_parameters.training_method[model_parameters_i]
        activation = model_parameters.activation[model_parameters_i]

        train_folds = folds != fold
        val_folds = torch.logical_not(train_folds)
        X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
        Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

        model, training_time, training_epochs = train_sgd_mlp(X_train=X_train,
                                                              Y_train=Y_train,
                                                              X_val=X_val,
                                                              Y_val=Y_val,
                                                              activation=activation,
                                                              training_method=training_method,
                                                              hidden_dims=[1000] * 3,
                                                              batch_size=50,
                                                              verbose=True,
                                                              patience=5,
                                                              max_epochs=100)

        train_metrics = evaluate_sgd(model=model,
                                     x=X_train,
                                     y=Y_train,
                                     )

        val_metrics = evaluate_sgd(model=model,
                                   x=X_val,
                                   y=Y_val,
                                   )
        test_metrics = evaluate_sgd(model=model,
                                    x=X_test,
                                    y=Y_test,
                                    )
        if verbose:
            print(train_metrics)
            print(val_metrics)
            print(test_metrics)

        out = {
            'dataset': dataset_i,
            'training_method': training_method,
            'fold': fold,
            'activation': activation,
            'train_auc': train_metrics[0].item(),
            'train_acc': train_metrics[1].item(),
            'train_prec': train_metrics[2].item(),
            'train_recall': train_metrics[3].item(),
            'train_f1': train_metrics[4].item(),
            'val_auc': val_metrics[0].item(),
            'val_acc': val_metrics[1].item(),
            'val_prec': val_metrics[2].item(),
            'val_recall': val_metrics[3].item(),
            'val_f1': val_metrics[4].item(),
            'test_auc': test_metrics[0].item(),
            'test_acc': test_metrics[1].item(),
            'test_prec': test_metrics[2].item(),
            'test_recall': test_metrics[3].item(),
            'test_f1': test_metrics[4].item(),
            'training_time': training_time,
            "training_epochs": training_epochs,
        }
        sgd_mlp_experiments.append(out)

sgd_mlp_experiments = pd.DataFrame(sgd_mlp_experiments)
output_file = os.path.join(output_dir, "sgd_mlp_experiments.csv")
sgd_mlp_experiments.to_csv(path_or_buf=output_file)


# </editor-fold>

# <editor-fold desc="SGD conv1d experiments">

model_parameters = expand_grid({
    'fold': list(range(5)),
    'activation': sgd_activations,
    'training_method': ["backprop", 'local_supervision', "forward_forward", ],
})

conv1d_datasets = ['ptbxl_mi', "human_nontata_promoters"]

verbose = False

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
sgd_conv1d_experiments = []
for dataset_i in conv1d_datasets:

    print(dataset_i)
    X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i,
                                                                 channels_last=False)

    for model_parameters_i in range(len(model_parameters)):
        print(model_parameters_i)

        fold = model_parameters.fold[model_parameters_i]
        activation = model_parameters.activation[model_parameters_i]
        training_method = model_parameters.training_method[model_parameters_i]
        hidden_dim = 32
        n_blocks = 4
        hidden_dims = [hidden_dim * 2 ** (i // 2) for i in range(n_blocks * 2)]

        train_folds = folds != fold
        val_folds = torch.logical_not(train_folds)
        X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
        Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

        model, training_time, training_epochs = train_sgd_conv1d(
            X_train=X_train,
            Y_train=Y_train,
            X_val=X_val,
            Y_val=Y_val,
            hidden_dims=hidden_dims,
            activation=activation,
            training_method=training_method,
            verbose=True)

        train_metrics = evaluate_sgd(model=model,
                                     x=X_train,
                                     y=Y_train,
                                     )

        val_metrics = evaluate_sgd(model=model,
                                   x=X_val,
                                   y=Y_val,
                                   )

        test_metrics = evaluate_sgd(model=model,
                                    x=X_test,
                                    y=Y_test,
                                    )
        if verbose:
            print(training_method, dataset_i, activation, sep="\n")
            print(train_metrics)
            print(val_metrics)
            print(test_metrics)

        out = {
            'dataset': dataset_i,
            'training_method': training_method,
            'fold': fold,
            'activation': activation,
            'hidden_dim': hidden_dim,
            'n_blocks': n_blocks,
            'train_auc': train_metrics[0].item(),
            'train_acc': train_metrics[1].item(),
            'train_prec': train_metrics[2].item(),
            'train_recall': train_metrics[3].item(),
            'train_f1': train_metrics[4].item(),
            'val_auc': val_metrics[0].item(),
            'val_acc': val_metrics[1].item(),
            'val_prec': val_metrics[2].item(),
            'val_recall': val_metrics[3].item(),
            'val_f1': val_metrics[4].item(),
            'test_auc': test_metrics[0].item(),
            'test_acc': test_metrics[1].item(),
            'test_prec': test_metrics[2].item(),
            'test_recall': test_metrics[3].item(),
            'test_f1': test_metrics[4].item(),
            'training_time': training_time,
            'training_epochs': training_epochs,
        }
        sgd_conv1d_experiments.append(out)

sgd_conv1d_experiments = pd.DataFrame(sgd_conv1d_experiments)
output_file = os.path.join(output_dir, "sgd_conv1d_experiments.csv")
sgd_conv1d_experiments.to_csv(path_or_buf=output_file)

# </editor-fold>

# <editor-fold desc="conv2d few-shot experiments (forward and SGD)">

forward_training_methods = ["forward_projection", "random", "label_projection", "noisy_label_projection"]
sgd_training_methods = ["backprop", "local_supervision", "forward_forward"]
all_training_methods = forward_training_methods + sgd_training_methods

experiment_parameters = expand_grid({
    'rep': list(range(50)),
    'n_sample': [5, 10, 15, 20, 30, 40, 50]
})

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
conv2d_experiments = []
for dataset_i in ['cxr', 'oct']:

    print(dataset_i)
    X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i, img_size=128, channels_last=True)
    hidden_dim = 16
    n_blocks = 4
    hidden_dims = [hidden_dim * 2 ** (i // 2) for i in range(n_blocks * 2)]
    activation = "relu"
    train_folds = folds != 0
    val_folds = torch.logical_not(train_folds)
    X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
    Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

    for experiment_parameters_i in range(len(experiment_parameters)):

        print(dataset_i, experiment_parameters_i)

        rep = experiment_parameters.rep[experiment_parameters_i]
        n_sample = experiment_parameters.n_sample[experiment_parameters_i]

        for training_method in all_training_methods:

            n_train = round(n_sample * 0.8)
            n_val = n_sample - n_train

            X_train_s, Y_train_s = subsample_dataset(X_train,
                                                     Y_train,
                                                     n_sample=n_train)
            X_val_s, Y_val_s = subsample_dataset(X_train,
                                                 Y_train,
                                                 n_sample=n_val)

            if training_method in ["forward_projection", "random", "label_projection", "noisy_label_projection"]:

                X_trainval_s = torch.concatenate([X_train_s, X_val_s])
                Y_trainval_s = torch.concatenate([Y_train_s, Y_val_s])

                w_list, _, _, training_time = train_forward_conv2d(x=X_trainval_s,
                                                                   y=Y_trainval_s,
                                                                   training_method=training_method,
                                                                   hidden_dim=hidden_dim,
                                                                   activation=activation,
                                                                   n_blocks=n_blocks,
                                                                   device=device,
                                                                   reg_factor=10,
                                                                   batch_size=5
                                                                   )
                train_metrics = evaluate_forward_conv2d(x=X_trainval_s,
                                                        y=Y_trainval_s,
                                                        w_list=w_list,
                                                        activation=activation)
                test_metrics = evaluate_forward_conv2d(x=X_test,
                                                       y=Y_test,
                                                       w_list=w_list,
                                                       activation=activation,
                                                       batch_size=50)


            else:

                model, training_time, training_epochs = train_sgd_conv2d(
                    X_train=X_train_s.transpose(1, -1),
                    Y_train=Y_train_s,
                    X_val=X_val_s.transpose(1, -1),
                    Y_val=Y_val_s,
                    hidden_dims=hidden_dims,
                    activation=activation,
                    training_method=training_method,
                    lr=0.0001,
                    batch_size=25,
                    patience=10,
                    verbose=True)

                train_metrics = evaluate_sgd(model=model,
                                             x=X_train_s.transpose(1, -1),
                                             y=Y_train_s,
                                             )

                val_metrics = evaluate_sgd(model=model,
                                           x=X_val_s.transpose(1, -1),
                                           y=Y_val_s,
                                           )

                test_metrics = evaluate_sgd(model=model,
                                            x=X_test.transpose(1, -1),
                                            y=Y_test,
                                            )

            print(training_method, n_sample)
            print(train_metrics)
            print(test_metrics)

            out = {
                'dataset': dataset_i,
                'training_method': training_method,
                'activation': activation,
                'hidden_dim': hidden_dim,
                'n_blocks': n_blocks,
                'n_sample': n_sample,
                'train_auc': train_metrics[0].item(),
                'train_acc': train_metrics[1].item(),
                'test_auc': test_metrics[0].item(),
                'test_acc': test_metrics[1].item(),
                'training_time': training_time,
            }
            conv2d_experiments.append(out)

conv2d_experiments = pd.DataFrame(conv2d_experiments)
output_file = os.path.join(output_dir, "conv2d_experiments.csv")
conv2d_experiments.to_csv(path_or_buf=output_file)

# </editor-fold

# <editor-fold desc="Dependence on output layer dimension">

dataset_i = "FashionMNIST"
print(dataset_i)
X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i)

model_parameters = expand_grid({
    'fold': list(range(5)),
    'training_method': ["forward_projection", "random", "label_projection", "noisy_label_projection", "forward_forward",
                        "local_supervision", "backprop"],
    'activation': ["relu"],
    'output_dim': [100, 200, 400, 800]
})
output_dim_experiments = []
verbose = True

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
for model_parameters_i in range(len(model_parameters)):
    print(model_parameters_i)

    training_method = model_parameters.training_method[model_parameters_i]
    activation = model_parameters.activation[model_parameters_i]
    output_dim = model_parameters.output_dim[model_parameters_i]
    hidden_dims = [1000, 1000, output_dim]

    fold = model_parameters.fold[model_parameters_i]
    train_folds = folds != fold
    val_folds = torch.logical_not(train_folds)
    X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
    Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

    w_list, _, _, training_time = train_forward_mlp(x=X_train,
                                                    y=Y_train,
                                                    training_method=training_method,
                                                    activation=activation,
                                                    hidden_dims=hidden_dims,
                                                    )
    training_epochs = 1
    train_metrics = evaluate_forward_mlp(x=X_train,
                                         y=Y_train,
                                         w_list=w_list,
                                         activation=activation,
                                         )

    val_metrics = evaluate_forward_mlp(x=X_val,
                                       y=Y_val,
                                       w_list=w_list,
                                       activation=activation,
                                       )

    test_metrics = evaluate_forward_mlp(x=X_test,
                                        y=Y_test,
                                        w_list=w_list,
                                        activation=activation,
                                        )
    if verbose:
        print(training_method)
        print(activation)
        print(train_metrics)
        print(val_metrics)
        print(test_metrics)

    out = {
        'dataset': dataset_i,
        'training_method': training_method,
        'fold': fold,
        'activation': activation,
        'output_dim': output_dim,
        'train_auc': train_metrics[0].item(),
        'train_acc': train_metrics[1].item(),
        'train_prec': train_metrics[2].item(),
        'train_recall': train_metrics[3].item(),
        'train_f1': train_metrics[4].item(),
        'val_auc': val_metrics[0].item(),
        'val_acc': val_metrics[1].item(),
        'val_prec': val_metrics[2].item(),
        'val_recall': val_metrics[3].item(),
        'val_f1': val_metrics[4].item(),
        'test_auc': test_metrics[0].item(),
        'test_acc': test_metrics[1].item(),
        'test_prec': test_metrics[2].item(),
        'test_recall': test_metrics[3].item(),
        'test_f1': test_metrics[4].item(),
        'training_time': training_time,
        "training_epochs": 1,
    }
    output_dim_experiments.append(out)

output_dim_experiments = pd.DataFrame(output_dim_experiments)
output_file = os.path.join(output_dir, "output_dim_experiments_.csv")
output_dim_experiments.to_csv(path_or_buf=output_file)

# </editor-fold>

# <editor-fold desc="Explainability Experiments and Visualisations">

# <editor-fold desc="MLP explainability">

import matplotlib.pyplot as plt

image_dir = output_dir

verbose = False
model_parameters = expand_grid({

    'fold': list(range(5)),
    'training_method': ["forward_projection"],
    'activation': ['relu', ],
    'hidden_dim': [1000, ],
})

dataset_i = "FashionMNIST"
explainability_mlp_experiments = []
print(dataset_i)
X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i)
for model_parameters_i in range(len(model_parameters)):
    print(model_parameters_i)

    fold = model_parameters.fold[model_parameters_i]
    training_method = model_parameters.training_method[model_parameters_i]
    activation = model_parameters.activation[model_parameters_i]
    reg_factor = model_parameters.hidden_dim[model_parameters_i]

    n_hidden_layers = 4
    hidden_dims = [1000] * n_hidden_layers

    train_folds = folds != fold
    val_folds = torch.logical_not(train_folds)
    X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
    Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]
    w_list, q_list, u_list, training_time = train_forward_mlp(x=X_train,
                                                              y=Y_train,
                                                              training_method=training_method,
                                                              activation=activation,
                                                              hidden_dims=[1000, 1000, 1000],
                                                              return_qu=True,
                                                              )

    test_metrics = evaluate_explanations_forward_mlp(x=X_test,
                                                     y=Y_test,
                                                     activation=activation,
                                                     w_list=w_list,
                                                     q_list=q_list,
                                                     u_list=u_list,
                                                     input_dependent=True)
    print(test_metrics)

    for i in range(n_hidden_layers):
        out_i = {
            'layer': i + 1,
            'activation': activation,
            'test_acc': test_metrics[i][1].item()
        }
        explainability_mlp_experiments.append(out_i)

explainability_mlp_experiments = pd.DataFrame(explainability_mlp_experiments)
output_file = os.path.join(output_dir, "explainability_mlp_experiments.csv")
explainability_mlp_experiments.to_csv(path_or_buf=output_file)

# </editor-fold>

# <editor-fold desc="Explainability conv1d Visualisation">

verbose = False
model_parameters = expand_grid({

    'fold': list(range(5)),
    'training_method': ["forward_projection"],
    'activation': ['relu', ],
})

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
dataset_i = "ptbxl_mi"
X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i)

model_parameters_i = 0
training_method = model_parameters.training_method[model_parameters_i]
fold = model_parameters.fold[model_parameters_i]
activation = model_parameters.activation[model_parameters_i]
hidden_dim = 32
n_blocks = 4
kernel_size = 3

# train 1d conv
train_folds = folds != fold
val_folds = torch.logical_not(train_folds)
X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
w_list, q_list, u_list, training_time = train_forward_conv1d(x=X_train,
                                                             y=Y_train,
                                                             training_method=training_method,
                                                             hidden_dim=hidden_dim,
                                                             activation=activation,
                                                             n_blocks=n_blocks,
                                                             device=device,
                                                             batch_size=1000,
                                                             return_qu=True,
                                                             )

selected_idx = [30, 615, 70, 0]
x = X_test[selected_idx].to(device)
activation_fn = activation_dict[activation]
ecg_underlay = x.to("cpu").numpy()
yhats = []
timesteps = []
timestep = torch.arange(x.shape[1])[None, :, None]
input_dependent = False
for l in range(len(w_list) - 1):
    # convolution and pooling
    stride = 2 - ((l + 1) % 2)
    if (l % 1) == 0:
        x = torch.nn.functional.pad(x, pad=(0, 0, 2, 0, 0, 0))
    x = x.unfold(dimension=1, size=kernel_size, step=stride).flatten(start_dim=2)
    x = concatenate_ones(x)

    z = x @ w_list[l]
    if input_dependent:
        g_a_q = torch.sign(x @ q_list[l])
        yhat = torch.tanh(z - g_a_q) @ torch.linalg.pinv(u_list[l])
    else:
        yhat = z @ torch.linalg.pinv(u_list[l])

    yhats.append(yhat)
    x = activation_fn(z)

for l in range(len(yhats) - 1):
    yhat_l = yhats[l]
    expansion = ecg_underlay.shape[1] // yhat_l.shape[1]
    yhat_l = yhat_l.permute(dims=(0, 2, 1))
    yhat_l = torch.nn.Upsample(scale_factor=(expansion,), mode="linear")(yhat_l)
    yhat_l = yhat_l.permute(dims=(0, 2, 1))
    yhats[l] = yhat_l.to("cpu").numpy()

plt.close()
fig, axs = plt.subplots(4, 4)

y_lim_input = [-6, 6.3]
y_lim2 = [-0.1, 1.5]
y_lim4 = [-0.1, 1.5]
y_lim6 = [-0.1, 1.1]
interval_colour = "red"
fp_colour = "#7570B3"

example_idx = 0
start_time = 360
end_time = start_time + 250
intervals = ((40, 70), (175, 210))
for interval_i in intervals:
    axs[0, example_idx].axes.axvspan(interval_i[0], interval_i[1], alpha=0.1, color=interval_colour)
for interval_i in intervals:
    for j in range(1, 4):
        axs[j, example_idx].axes.axvspan(interval_i[0] / 100, interval_i[1] / 100, alpha=0.1, color=interval_colour)

axs[0, example_idx].plot(np.arange(end_time - start_time),
                         ecg_underlay[example_idx, start_time:end_time, 11], color="black")
axs[0, example_idx].axes.get_xaxis().set_visible(False)
axs[0, example_idx].set_ylim(y_lim_input)
axs[0, example_idx].axes.set_ylabel("Input\n(mV)", rotation=0, labelpad=10)
axs[0, example_idx].axes.set_title("Patient A\nLead v6")

axs[1, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[2][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[1, example_idx].axes.set_xlabel("Time (s)")
axs[1, example_idx].axes.set_ylabel('$\hat{y}_2$', fontsize=14, rotation=0, labelpad=10)
axs[1, example_idx].set_ylim(y_lim2)
axs[1, example_idx].xaxis.set_ticks(np.arange(3))

axs[2, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[4][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[2, example_idx].axes.set_xlabel("Time (s)")
axs[2, example_idx].axes.set_ylabel('$\hat{y}_4$', fontsize=14, rotation=0, labelpad=10)
axs[2, example_idx].set_ylim(y_lim4)
axs[2, example_idx].xaxis.set_ticks(np.arange(3))

axs[3, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[6][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[3, example_idx].axes.set_xlabel("Time (s)")
axs[3, example_idx].axes.set_ylabel('$\hat{y}_6$', fontsize=14, rotation=0, labelpad=10)
axs[3, example_idx].set_ylim(y_lim6)
axs[3, example_idx].xaxis.set_ticks(np.arange(3))

example_idx = 1
start_time = 640
end_time = start_time + 250

axs[0, example_idx].cla()

intervals = ((55, 75), (135, 157), (218, 238))
for interval_i in intervals:
    axs[0, example_idx].axes.axvspan(interval_i[0], interval_i[1], alpha=0.1, color=interval_colour)
for interval_i in intervals:
    for j in range(1, 4):
        axs[j, example_idx].axes.axvspan(interval_i[0] / 100, interval_i[1] / 100, alpha=0.1, color=interval_colour)

axs[0, example_idx].plot(np.arange(end_time - start_time),
                         ecg_underlay[example_idx, start_time:end_time, 7], color="black")
axs[0, example_idx].set_ylim(y_lim_input)

axs[0, example_idx].axes.set_title("Patient B\nLead v1")

axs[1, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[2][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[1, example_idx].set_ylim(y_lim2)
axs[1, example_idx].axes.set_xlabel("Time (s)")
axs[1, example_idx].xaxis.set_ticks(np.arange(3))

axs[2, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[4][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[2, example_idx].set_ylim(y_lim4)
axs[2, example_idx].axes.set_xlabel("Time (s)")
axs[2, example_idx].xaxis.set_ticks(np.arange(3))

axs[3, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[6][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[3, example_idx].axes.set_xlabel("Time (s)")
axs[3, example_idx].set_ylim(y_lim6)
axs[3, example_idx].xaxis.set_ticks(np.arange(3))

example_idx = 2
start_time = 120
end_time = start_time + 250

intervals = ((25, 55), (107, 137), (198, 225))
for interval_i in intervals:
    axs[0, example_idx].axes.axvspan(interval_i[0], interval_i[1], alpha=0.1, color=interval_colour)
for interval_i in intervals:
    for j in range(1, 4):
        axs[j, example_idx].axes.axvspan(interval_i[0] / 100, interval_i[1] / 100, alpha=0.1, color=interval_colour)

axs[0, example_idx].plot(np.arange(end_time - start_time),
                         ecg_underlay[example_idx, start_time:end_time, 0], color="black")
axs[0, example_idx].set_ylim(y_lim_input)
axs[0, example_idx].axes.set_title("Patient C\nLead I")

axs[1, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[2][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[1, example_idx].axes.set_xlabel("Time (s)")
axs[1, example_idx].set_ylim(y_lim2)
axs[1, example_idx].xaxis.set_ticks(np.arange(3))

axs[2, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[4][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[2, example_idx].axes.set_xlabel("Time (s)")
axs[2, example_idx].set_ylim(y_lim4)
axs[2, example_idx].xaxis.set_ticks(np.arange(3))

axs[3, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[6][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[3, example_idx].axes.set_xlabel("Time (s)")
axs[3, example_idx].set_ylim(y_lim6)
axs[3, example_idx].xaxis.set_ticks(np.arange(3))

example_idx = 3
start_time = 160
end_time = start_time + 250
axs[0, example_idx].plot(np.arange(end_time - start_time),
                         ecg_underlay[example_idx, start_time:end_time, 6], color="black")
axs[0, example_idx].set_ylim(y_lim_input)
axs[0, example_idx].axes.set_title("Patient D\nLead v1")

axs[1, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[2][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[1, example_idx].axes.set_xlabel("Time (s)")
axs[1, example_idx].set_ylim(y_lim2)
axs[1, example_idx].xaxis.set_ticks(np.arange(3))

axs[2, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[4][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[2, example_idx].axes.set_xlabel("Time (s)")
axs[2, example_idx].set_ylim(y_lim4)
axs[2, example_idx].xaxis.set_ticks(np.arange(3))

axs[3, example_idx].plot(np.arange(end_time - start_time) / 100,
                         yhats[6][example_idx, start_time:end_time, 1],
                         color=fp_colour)
axs[3, example_idx].axes.set_xlabel("Time (s)")
axs[3, example_idx].set_ylim(y_lim6)
axs[3, example_idx].xaxis.set_ticks(np.arange(3))

for i in range(3):
    for j in range(4):
        axs[i, j].axes.get_xaxis().set_visible(False)

for i in range(4):
    for j in range(1, 4):
        axs[i, j].axes.get_yaxis().set_visible(False)

plt.tight_layout()
plt.savefig(fname=os.path.join(output_dir, "Figure_3_PTBXL_attn.pdf"),
            dpi=1200
            )

# </editor-fold>

# <editor-fold desc="Explainability Conv2d visualisation">

img_size = 128
dataset_i = "oct"
explainability_mlp_experiments = []
print(dataset_i)
seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
X_trainval, Y_trainval, X_test, Y_test, folds = load_dataset(dataset_i, img_size=img_size)

train_folds = folds != 0
val_folds = torch.logical_not(train_folds)
X_train, X_val = X_trainval[train_folds], X_trainval[val_folds]
Y_train, Y_val = Y_trainval[train_folds], Y_trainval[val_folds]

seed = 0
random.seed(seed)
torch.manual_seed(seed)
np.random.seed(seed)
attn_maps = [torch.zeros(1, 1, 1, 1)] * 3
for rep_i in range(5):

    print(rep_i)

    n_sample = 100
    n_train = round(n_sample * 0.8)
    n_val = n_sample - n_train

    X_train_s, Y_train_s = subsample_dataset(X_train,
                                             Y_train,
                                             n_sample=n_train)
    X_val_s, Y_val_s = subsample_dataset(X_train,
                                         Y_train,
                                         n_sample=n_val)

    X_trainval_s = torch.concatenate([X_train_s, X_val_s])
    Y_trainval_s = torch.concatenate([Y_train_s, Y_val_s])

    hidden_dim = 32
    n_blocks = 4
    activation = "relu"
    training_method = "forward_projection"
    seed = rep_i
    random.seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    n_sample_test = 10
    w_list, q_list, u_list, training_time = train_forward_conv2d(x=X_trainval_s,
                                                                 y=Y_trainval_s,
                                                                 training_method=training_method,
                                                                 hidden_dim=hidden_dim,
                                                                 activation=activation,
                                                                 n_blocks=n_blocks,
                                                                 device=device,
                                                                 reg_factor=10,
                                                                 batch_size=5,
                                                                 return_qu=True,
                                                                 )

    seed = 2
    random.seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    n_sample_test = 3
    X_test_s, Y_test_s = subsample_dataset(X_test, Y_test, n_sample=n_sample_test)

    x_img = X_test_s.to(device)
    x = torch.clone(x_img)
    activation_fn = torch.relu

    resize_transform = torchvision.transforms.Resize(size=(img_size, img_size))

    kernel_size = 3
    for l in range(6):

        # pooling
        stride = 2 - ((l + 1) % 2)
        x = x.unfold(dimension=1, size=kernel_size, step=stride)  #
        x = x.unfold(dimension=2, size=kernel_size, step=stride)  #
        x = x.flatten(start_dim=3)
        x = concatenate_ones(x)

        x_pre = torch.clone(x)

        z = x @ w_list[l]

        if l % 2 == 1:
            g_a_q = torch.sign(x_pre @ q_list[l])
            yhat = torch.tanh(z - g_a_q) @ torch.linalg.pinv(u_list[l])
            yhat = resize_transform(yhat.permute((0, 3, 1, 2))).permute((0, 2, 3, 1))
            attn_maps[l // 2] = attn_maps[l // 2] + yhat.to("cpu")

        x = activation_fn(z)

attn_maps = [torch.softmax(i, dim=-1) ** 3 for i in attn_maps]

plt.close()
fig, axes = plt.subplots(4, 4)
plt.setp(axes, xticks=[], yticks=[])
examples = [n_sample_test + 0, n_sample_test + 1, n_sample_test + 2, 0, ]

vmin_list = [attn_i.min() for attn_i in attn_maps]
vmax_list = [attn_i.max() for attn_i in attn_maps]

for j in range(4):

    example_j = examples[j]

    x_i = -x_img[example_j, :, :, 0].cpu().numpy()

    for i in range(4):
        axes[i, j].imshow(x_i, cmap="Greys")

    for i in range(3):
        attn_i = attn_maps[i][example_j, :, :, 1].cpu().numpy()
        axes[i + 1, j].imshow(attn_i,
                              alpha=0.5,
                              vmin=vmin_list[i],
                              vmax=vmax_list[i], cmap="rainbow",
                              interpolation='nearest'
                              )

axes[0, 0].set_ylabel("Input", rotation=0, labelpad=35)
axes[1, 0].set_ylabel("$\hat{y}_2$", fontsize=14, rotation=0, labelpad=35)
axes[2, 0].set_ylabel("$\hat{y}_4$", fontsize=14, rotation=0, labelpad=35)
axes[3, 0].set_ylabel("$\hat{y}_6$", fontsize=14, rotation=0, labelpad=35)

for j in range(4):
    axes[0, j].set_title("Patient " + ["A", "B", "C", "D"][j])

plt.tight_layout()

plt.savefig(
    os.path.join(output_dir, "Figure_4_OCT_attn.pdf"),
    dpi=600
)
plt.savefig(
    os.path.join(output_dir, "Figure_4_OCT_attn.png"),
    dpi=600
)

# </editor-fold>

# </editor-fold>

# <editor-fold desc="Organising results tables">

training_method_names = {
    "forward_projection": "FP",
    "random": "Random",
    "label_projection": "LP",
    "noisy_label_projection": "LPN",
    "local_supervision": "LS",
    "forward_forward": "FF",
    "backprop": "BP",
}


pd.options.mode.copy_on_write = True

results_files = [os.path.join(output_dir, i) for i in os.listdir(output_dir) if
                 "_experiments.csv" in i]
results_tables = [pd.read_csv(i, index_col=0, header=0) for i in results_files]
mlp_tables = pd.concat([results_tables[i] for i in range(5) if "mlp" in results_files[i]])
conv1d_tables = [results_tables[i] for i in range(5) if "conv1d" in results_files[i]]
conv1d_tables[0]["training_epochs"] = 1
conv1d_tables = pd.concat(conv1d_tables)
conv1d_tables = conv1d_tables.drop(['hidden_dim', 'n_blocks'], axis=1)
all_tables = pd.concat([mlp_tables, conv1d_tables])

all_tables.columns = all_tables.columns.str.replace("_", " ")
all_tables.columns = all_tables.columns.str.title()
all_tables.columns = [x.replace("Training Method", "Method") for x in all_tables.columns]
all_tables.columns = [x.replace("Test ", "") for x in all_tables.columns]
all_tables.columns = [x.replace("Auc", "AUC") for x in all_tables.columns]
all_tables.Method = all_tables.Method.replace(training_method_names)
all_tables.Method = pd.Categorical(all_tables.Method,
                                   categories=training_method_names.values())

all_tables.Dataset = all_tables.Dataset.replace({"ptbxl_mi": "PTBXL-MI", "human_nontata_promoters": "Promoters"})
all_tables = all_tables.loc[all_tables.Dataset.isin(['FashionMNIST', 'Promoters', 'PTBXL-MI'])].reset_index()
all_tables.Dataset = pd.Categorical(all_tables.Dataset, categories=['FashionMNIST', 'Promoters', 'PTBXL-MI'])

#relu activated performance
all_perf = all_tables.loc[all_tables.Activation == "relu"]
all_perf = all_perf.loc[all_perf.Method.isin(['FP', 'Random', 'LS', 'FF', 'BP'])]
all_perf = all_perf.drop(labels=["Activation"], axis=1)
all_perf = all_perf.groupby(['Dataset', 'Method', ], observed=True).aggregate(mean_sd_func2)[['Acc', "AUC", ]]
all_perf = pd.melt(all_perf, ignore_index=False,
                   var_name='Metric')  # id_vars=['dataset', 'training_method',  'activation'])
all_perf.reset_index(inplace=True)
all_perf = all_perf.pivot(index=["Dataset", "Metric", ],
                          columns="Method",
                          values=["value"]
                          )

all_perf.to_csv(os.path.join(output_dir, "Table_1_main_results.csv"))
all_perf.to_latex(os.path.join(output_dir, "Table_1_main_results.tex"))

# mod2 and square activated performance
all_perf = all_tables.copy()
all_perf = all_perf.loc[all_perf.Method.isin(['FP', "LS", "FF", 'BP'])]
all_perf = all_perf.loc[all_perf.Activation.isin(["mod2", "square"])]
all_perf.Activation = all_perf.Activation.replace({"sign_surrogate": "sign"})
all_perf = all_perf.groupby(['Dataset', 'Method', 'Activation'], observed=True).aggregate(mean_sd_func2)[['Acc']]
all_perf = pd.melt(all_perf, ignore_index=False,
                   var_name='Metric')  # id_vars=['dataset', 'training_method',  'activation'])
all_perf.reset_index(inplace=True)
all_perf = all_perf.pivot(index=["Dataset", 'Activation'],
                          columns="Method",
                          values=["value"]
                          )
all_perf.to_csv(os.path.join(output_dir, "Table_A1_alternative_activations.csv"))
all_perf.to_latex(os.path.join(output_dir, "Table_A1_alternative_activations.tex"))


#conv2d few shot experiments
conv2d_experiments_file = os.path.join(output_dir, "conv2d_experiments.csv")
all_tables = pd.read_csv(conv2d_experiments_file, index_col=0)

all_tables.columns = all_tables.columns.str.replace("_", " ")
all_tables.columns = all_tables.columns.str.title()
all_tables.columns = [x.replace("Training Method", "Method") for x in all_tables.columns]
all_tables.columns = [x.replace("Auc", "AUC") for x in all_tables.columns]
all_tables.Method = all_tables.Method.replace(training_method_names)
all_tables.Method = pd.Categorical(all_tables.Method,
                                   categories=training_method_names.values())
all_tables.Dataset = pd.Categorical(all_tables.Dataset,
                                    categories={"cxr": "CXR", "oct": "OCT"})
n_sample_values = all_tables['N Sample'].unique().tolist()
all_tables['N Sample'] = "N=" + all_tables['N Sample'].astype(str)
all_tables['N Sample'] = pd.Categorical(all_tables['N Sample'], categories=["N=" + str(i) for i in n_sample_values])
#all_tables = all_tables.drop(labels=["Activation"], axis=1)

all_perf = all_tables.copy()
all_perf = all_perf.loc[all_perf.Method.isin(["FP", "RF", "LS", "FF", "BP"]), :]
all_perf = all_perf = all_perf.drop(labels=["Activation"], axis=1)
all_perf = all_perf.groupby(['Dataset', 'Method', "N Sample"], observed=True).aggregate(mean_sd_func2)[["Train AUC", "Test AUC"]]
all_perf = pd.melt(all_perf, ignore_index=False,
                   var_name='Metric')
all_perf.reset_index(inplace=True)
all_perf.Metric = pd.Categorical(all_perf.Metric, categories=["Train AUC", "Test AUC"])
all_perf = all_perf.pivot(index=["Dataset",  "Metric", "N Sample"],
                          columns="Method",
                          values=["value"]
                          )

all_perf.to_csv(os.path.join(output_dir, "Table_A2_fewshot_performance.csv"))
all_perf.to_latex(os.path.join(output_dir, "Table_A2_fewshot_perf.tex"))


# </editor-fold>
