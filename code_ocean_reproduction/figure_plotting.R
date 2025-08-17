#plotting fp codeocean submission 16_08_25


library(ggplot2)
library(ggrepel)
library(RColorBrewer)
library(ggpubr)
library(latex2exp)

output_dir <- "results"

#figure 2 main methods
if(T){
  
  label_size=2.35
  
  #CXR OCT and CIFAR fewshot experiments
  df_i <- read.csv(file.path(output_dir, "conv2d_experiments.csv"))
  df_i$training_method[df_i$training_method=="forward_forward"] <- "FF"
  df_i$training_method[df_i$training_method=="forward_projection"] <- "FP"
  df_i$training_method[df_i$training_method=="backprop"] <- "BP"
  df_i$training_method[df_i$training_method=="label_projection"] <- "LP"
  df_i$training_method[df_i$training_method=="noisy_label_projection"] <- "LPN"
  df_i$training_method[df_i$training_method=="local_supervision"] <- "LS"
  df_i$training_method[df_i$training_method=="random"] <- "RF"
  df_i$training_method[df_i$training_method=="difference_target_propagation"] <- "DTP"
  df_i$training_method[df_i$training_method=="predictive_coding"] <- "PC"
  
  df_i$dataset[df_i$dataset=="oct"] <- "OCT"
  df_i$dataset[df_i$dataset=="cxr"] <- "CXR"
  
  training_method_levels <- c("BP", "FF", "FP", "LP", "LPN", "LS", "RF")
  df_i$training_method <- factor(df_i$training_method, training_method_levels)
  myColors <- brewer.pal(7,"Dark2")
  myColors2 <- c("darkorchid3", "black")
  myColors <- c(myColors, myColors2)
  names(myColors) <- training_method_levels
  colScale <- scale_colour_manual(name = "grp",values = myColors)
  
  
  df_i <- aggregate(df_i[,"test_auc",drop=F],
                    by=df_i[,c("n_sample","hidden_dim", "training_method", "dataset"),drop=F],
                    FUN=mean)
  selected_training_methods <- c("RF", "BP", "FF", "LS", "FP", "DTP", "PC")
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
                                      segment.color = 'grey',
                                      size=label_size
  )
  
  
  plot_cxr_fewshot <- plot_i
  ggsave(plot_cxr_fewshot,
         filename=file.path(output_dir, "CXR_conv2d_fewshot_performance.pdf"),
         dpi=300,
         width=4,
         height=4)
  

  
  #CIFAR experiments
  df_ii <- df_i[df_i$dataset=="CIFAR",]
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
    colScale+
    scale_x_continuous(breaks=c(25, 50,75, 100),)#+
  #ylim(c(0.47, 0.93))
  
  
  df_i_last = df_ii[df_ii$n_sample==max(df_ii$n_sample),]
  
  plot_i <- plot_i + geom_label_repel(data=df_i_last, aes(label = training_method),
                                      box.padding   = 0.35, 
                                      point.padding = 0.5,
                                      segment.color = 'grey',
                                      size=label_size
  )
  
  plot_cifar_fewshot <- plot_i
  ggsave(plot_cifar_fewshot,
         filename=file.path(output_dir, "CIFAR_conv2d_fewshot_performance.pdf"),
         dpi=300,
         width=4,
         height=4)
  
  
  
}


