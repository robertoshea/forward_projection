#plotting closed form randomised learning figures



library(ggplot2)
library(ggrepel)
library(RColorBrewer)
library(ggpubr)
library(latex2exp)


output_dir <- "/results"

#target gen toy diagram
if(T){
  
  n <- 100
  x1 = rnorm(n)
  x2 = x1 + rnorm(n)*0.6
  df_i = data.frame(x1, x2)
  
  toy_reg_plot <- ggplot(df_i, aes(x=x1, y=x2))+
    geom_point(colour="blue")+
    geom_smooth(method='lm', formula= y~x, colour="red", se = FALSE)+
    theme_classic()+
    ylab(TeX("$\\tilde{Z}_l$"))+
    xlab(TeX("$A_{l-1}$"))+
    theme(axis.title.y = element_text(angle = 0, vjust = 0.5),
          axis.ticks.x=element_blank(),
          axis.text.x=element_blank(),
          axis.ticks.y=element_blank(),
          axis.text.y=element_blank()
    )+
    annotate("text", x=2.6, y=3.,angle=45, label= TeX("$W_l$"))
  
  ggsave(toy_reg_plot,
         filename=file.path(output_dir, "toy_reg_plot.png"),
         dpi=600,
         width=2.5,
         height=2.5)

}

#figure 2
if(T){
  
  #CXR and OCT fewshot experiments
  df_i <- read.csv(file.path(output_dir, "conv2d_experiments.csv"))
  
  df_i$training_method[df_i$training_method=="forward_forward"] <- "FF"
  df_i$training_method[df_i$training_method=="forward_projection"] <- "FP"
  df_i$training_method[df_i$training_method=="backprop"] <- "BP"
  df_i$training_method[df_i$training_method=="label_projection"] <- "LP"
  df_i$training_method[df_i$training_method=="noisy_label_projection"] <- "LPN"
  df_i$training_method[df_i$training_method=="local_supervision"] <- "LS"
  df_i$training_method[df_i$training_method=="random"] <- "RF"
  df_i$dataset[df_i$dataset=="oct"] <- "OCT"
  df_i$dataset[df_i$dataset=="cxr"] <- "CXR"
  
  
  df_i$training_method <- factor(df_i$training_method)
  training_method_levels <- levels(df_i$training_method)
  myColors <- brewer.pal(length(training_method_levels),"Dark2")
  names(myColors) <- training_method_levels
  colScale <- scale_colour_manual(name = "grp",values = myColors)
  
  
  df_i <- aggregate(df_i[,"test_auc",drop=F],
                    by=df_i[,c("n_sample", "training_method", "dataset"),drop=F],
                    FUN=mean)
  selected_training_methods <- c("RF", "BP", "FF", "LS", "FP")
  df_i <- df_i[df_i$training_method %in% c(selected_training_methods),]
  
  df_ii <- df_i[df_i$dataset=="CXR",]
  plot_i <- ggplot(df_ii,
                   aes(x=n_sample, y=test_auc, colour=training_method))+
    geom_line()+
    geom_point()+
    xlab("N Train")+
    ylab("Test AUC")+
    labs(colour="Training Method")+
    theme_classic()+
    theme(panel.grid.major = element_blank(), 
          panel.grid.minor = element_blank(),
          axis.line=element_blank(),
          panel.background = element_rect(colour = "black"))+
    theme(legend.position = "none")+
    colScale
  
  
  df_i_last = df_ii[df_ii$n_sample==max(df_ii$n_sample),]
  
  plot_i <- plot_i + geom_label_repel(data=df_i_last, aes(label = training_method),
                                      box.padding   = 0.35, 
                                      point.padding = 0.5,
                                      segment.color = 'grey')
  
  
  plot_cxr_fewshot <- plot_i
  
  #OCT experiments
  df_ii <- df_i[df_i$dataset=="OCT",]
  plot_i <- ggplot(df_ii,
                   aes(x=n_sample, y=test_auc, colour=training_method))+
    geom_line()+
    geom_point()+
    xlab("N Train")+
    ylab("Test AUC")+
    labs(colour="Training Method")+
    theme_classic()+
    theme(panel.grid.major = element_blank(), 
          panel.grid.minor = element_blank(),
          axis.line=element_blank(),
          panel.background = element_rect(colour = "black"))+
    theme(legend.position = "none")+
    colScale
  
  
  df_i_last = df_ii[df_ii$n_sample==max(df_ii$n_sample),]
  
  plot_i <- plot_i + geom_label_repel(data=df_i_last, aes(label = training_method),
                                      box.padding   = 0.35, 
                                      point.padding = 0.5,
                                      segment.color = 'grey')
  
  
  plot_oct_fewshot <- plot_i
  
  #MLP output dimension experiments
  df_i <- read.csv(file.path(output_dir,
                             "output_dim_experiments.csv"))
  
  
  df_i$training_method[df_i$training_method=="forward_forward"] <- "FF"
  df_i$training_method[df_i$training_method=="forward_projection"] <- "FP"
  df_i$training_method[df_i$training_method=="backprop"] <- "BP"
  df_i$training_method[df_i$training_method=="label_projection"] <- "LP"
  df_i$training_method[df_i$training_method=="noisy_label_projection"] <- "LPN"
  df_i$training_method[df_i$training_method=="local_supervision"] <- "LS"
  df_i$training_method[df_i$training_method=="random"] <- "RF"
  
  df_i <- aggregate(df_i[,"test_acc",drop=F],
                    by=df_i[,c("output_dim", "training_method"),drop=F],
                    FUN=mean)
  
  df_i <- df_i[!df_i$training_method %in% c("BP", "FF", "LS"),]
  plot_i <- ggplot(df_i, aes(x=output_dim, y=test_acc, colour=training_method))+
    geom_line()+
    geom_point()+
    xlab("Hidden Layer Dimension")+
    ylab("Test Accuracy")+
    labs(colour="Training Method")+
    theme_classic()+
    theme(panel.grid.major = element_blank(), 
          panel.grid.minor = element_blank(),
          axis.line=element_blank(),
          panel.background = element_rect(colour = "black"))+
    theme(legend.position="none")+
    colScale
  
  df_i_last = df_i[df_i$output_dim==max(df_i$output_dim),]
  
  plot_i <- plot_i + geom_label_repel(data=df_i_last, aes(label = training_method),
                                      box.padding   = 0.35, 
                                      point.padding = 0.5,
                                      segment.color = 'grey')
  
  plot_fmnist_bottleneck <- plot_i
  
  
  #mlp explainability performance tables
  df_i <- read.csv(file.path(output_dir, "explainability_mlp_experiments.csv"))
  df_i$training_method <- "FP"
  df_i$layer <- df_i$layer+1
  
  
  plot_i <- ggplot(df_i, aes(x=layer, y=test_acc, colour=training_method))+
    stat_summary(fun = mean,
                 geom = "point") +
    stat_summary(fun = mean,
                 fun.min = function(x) mean(x) - sd(x), 
                 fun.max = function(x) mean(x) + sd(x), 
                 geom = "errorbar",
                 width=0) +
    stat_summary(fun = mean,
                 geom = "line") +
    
    xlab("Layer")+
    ylab("Test Accuracy")+
    theme_classic()+
    theme(panel.grid.major = element_blank(), 
          panel.grid.minor = element_blank(),
          axis.line=element_blank(),
          panel.background = element_rect(colour = "black"))+
    theme(legend.position="none")+
    colScale
  
  df_i_last = df_i[df_i$layer==max(df_i$layer),]
  df_i_last = df_i_last[1,,drop=F]
  plot_i <- plot_i + geom_label_repel(data=df_i_last, aes(label = training_method),
                                      box.padding   = 0.35, 
                                      point.padding = 0.5,
                                      segment.color = 'grey')
  
  plot_mlp_explain <- plot_i
  

  all_plots_1 <- ggarrange(plotlist=list(plot_fmnist_bottleneck,  plot_cxr_fewshot, plot_oct_fewshot, plot_mlp_explain),
                           labels = c("A",  "B", "C", "D"),
                           nrow=2, ncol=2)
  
  
  ggsave(all_plots_1,
         filename=file.path(output_dir, "Figure_2_performance_plots.pdf"),
         dpi=600,
         width=6,
         height=6)
}
