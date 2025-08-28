A Google Colab notebook is available to run sample experiments at https://colab.research.google.com/drive/1OuMsnpa2HTy71nW8ykhhhQ3UkD3sjiBQ?usp=sharing.
Experiments described in "Closed-Form Feedback-Free Learning with Forward Projection" may also be run with the python script provided in "code_ocean_reproduction/run_experiments.py". Note that, for brevity, this script runs a reduced number of experimental replicates, and examines a subset of methods. Instructions are provided in code comments at the beginning of each experiments section to allow all methods to be run.

Pre-processed datasets and splits are provided in compressed form at https://data.mendeley.com/datasets/fb7xddyxs4/2
Datasets can be automatically downloaded using the above "run_experiments.py" script, by setting auto_download=True in the first code section.

PTBXL data is sourced from:
Wagner, P. et al. PTB-XL, a large publicly available electrocardiography dataset.
Scientific Data 7 (2020). URL http://dx.doi.org/10.1038/s41597-020-0495-6.

Human NonTATA promoters data is sourced from:
Greˇsov´a, K., Martinek, V., ˇCech´ak, D., ˇSimeˇcek, P. & Alexiou, P. Genomic
benchmarks: a collection of datasets for genomic sequence classification. BMC
Genomic Data 24 (2023). URL http://dx.doi.org/10.1186/s12863-023-01123-8.

OCT and CXR datasets are sourced from:
Kermany, D. S. et al. Identifying medical diagnoses and treatable diseases by
image-based deep learning. Cell 172, 1122–1131.e9 (2018). URL http://dx.doi.org/10.1016/j.cell.2018.02.010.

#Example Usage

#model parameters
hidden_dim = 16 # number of conv2d filters in first layer of first block. x2 at each block.
activation = "relu"  #hidden activation function
n_blocks = 3  #number of convolutional blocks
n_outputs = 1 # number of output neurons, at present only set up for binary/multiclass classification
reg_factor = 10 #ridge regression penalty
batch_size = 50 #batch size is solely for memory management, and does not affect result

#Generate random data
#train_forward_conv2d expects channels last
n_train = 1000
n_test = 100
img_size = 28
n_channels = 3
X_train = torch.randn((n_train, img_size, img_size, n_channels))
Y_train = (torch.randn((n_test,))>0).type(torch.float32)

#fit weights and store in w_list
#q_list is the list of data projection matrices
#u_list is the list of label projection matrices
w_list, q_list, u_list, training_time = train_forward_conv2d(x=X_train,
                                                                   y=Y_train,
                                                                   training_method=training_method,
                                                                   hidden_dim=hidden_dim,
                                                                   activation=activation,
                                                                   n_blocks=n_blocks,
                                                                   device=device,
                                                                   reg_factor=reg_factor,
                                                                   batch_size=batch_size,
                                                                   return_qu=True
                                                                   )
train_metrics = evaluate_forward_conv2d(x=X_train,
                                        y=Y_train,
                                        w_list=w_list,
                                        activation=activation)


