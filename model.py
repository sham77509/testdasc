import tensorflow as tf
from tensorflow.keras import layers, Sequential, Model, Input
from tensorflow.keras import backend as K
from tensorflow.python.keras.layers import Layer
from tensorflow.python.keras.initializers import Initializer
from sklearn.cluster import SpectralClustering
import numpy as np
import os
import math
from scipy.linalg import qr
from itertools import combinations as comb
import tensorflow.python.keras.layers as nn
from tensorflow import math
# from scipy.sparse.linalg import svds
# from sklearn.preprocessing import normalize

import utils
import loss
# from DASC import utils
# from DASC import loss

tf.keras.backend.set_floatx('float32')
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)
# os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


  
class Self_Attn(Layer):
    """ Self attention Layer"""
    def __init__(self,in_dim,activation):
        super(Self_Attn,self).__init__()
        self.shape = in_dim
        self.activation = activation

        self.query_conv = nn.Conv2D(filters =in_dim //8 , kernel_size= 1)
        self.key_conv = nn.Conv2D(filters =in_dim //8 , kernel_size= 1)
        self.value_conv = nn.Conv2D(filters =in_dim, kernel_size= 1)
        self.logits = tf.Variable(tf.zeros(1))
        self.logits = tf.math.log_softmax(self.logits,axis=-1)
        # self.softmax  = tf.keras.layers.Softmax(dim=-1) #
    def call(self,x):
        """
            inputs :
                x : input feature maps( B X C X W X H)
            returns :
                out : self attention value + input feature
                attention: B X N X N (N is Width*Height)
        """
        m_batchsize,width ,height,C = self.shape
        proj_query  = self.query_conv(x).reshape((m_batchsize,-1,width*height)).permute(0,2,1) # B X CX(N)
        proj_key =  self.key_conv(x).reshape((m_batchsize,-1,width*height)) # B X C x (*W*H)
        energy =  tf.matmul(proj_query,proj_key) # transpose check
        attention = self.softmax(energy) # BX (N) X (N)
        proj_value = self.value_conv(x).reshape((m_batchsize,-1,width*height)) # B X C X N

        out = tf.matmul(proj_value,attention.permute(0,2,1) )
        out =out.reshape((m_batchsize,width,height,C))

        out = self.gamma*out + x
        return out
class Self_Expressive(Layer):
	def __init__(self, batch_size, **kwargs):
		super(Self_Expressive, self).__init__(**kwargs)
		self.batch_size = batch_size

	def build(self, input_shape):
		# ???????????????????????????????????????
		self.theta = self.add_weight(name='Theta',
									  shape=(1, self.batch_size, self.batch_size),
									  initializer=tf.keras.initializers.Constant(value=1e-8),
									  trainable=True)
		# self.bias = self.add_weight(name='bias',
		# 							shape=(1, self.batch_size, self.batch_size),
		# 							initializer='zeros',
		# 							trainable=True)
		super(Self_Expressive, self).build(input_shape)  # ???????????????????????????

	def call(self, x):
		z = K.dot(self.theta, x)
		# z = K.bias_add(z, self.bias)
		z = K.relu(z)
		return z

class U_initializer(Initializer):
	def __init__(self, matrix):
		self.matrix = matrix

	def __call__(self, shape, dtype=None):
		return K.variable(value=self.matrix, dtype=dtype)

class Projection(Layer):
	def __init__(self, matrix, **kwargs):
		super(Projection, self).__init__(**kwargs)
		self.matrix = matrix

	def build(self, input_shape):
		# ???????????????????????????????????????
		self.U = self.add_weight(name="_u",
									  shape=self.matrix.shape,
									  initializer=U_initializer(self.matrix),
									  trainable=True)
		super(Projection, self).build(input_shape)  # ???????????????????????????

	def call(self, z):
		# U = tf.keras.utils.normalize(U, axis=1, order=2)
		U = utils.u_normalize(self.U)
		z = K.dot(K.transpose(self.U), z)
		# z = K.relu(z)
		z = K.dot(self.U, z)
		# z = K.relu(z)
		return z

class ConvAE(Model):
	def __init__(self, input_shape=(1440, 32, 32, 1), batch_size=None):
		super(ConvAE, self).__init__()

		# self.input_shape = input_shape # [32, 32, 1] i.e. 32x32x1 ???????????????
		self.batch_size = batch_size
		# self.input_img = layers.Input(shape=input_shape)
		# COIL-20??????????????????????????????
		self.encoder = Sequential([
			layers.Conv2D(15, kernel_size=3,
						  activation='relu',
						  input_shape=input_shape[1:],
						  strides=2,
						  padding='SAME',
						  kernel_initializer = tf.keras.initializers.GlorotUniform(),
						  kernel_regularizer=tf.keras.regularizers.l1()),
			layers.Reshape((-1, 3840), trainable=False)
		])
		self.self_attention = Self_Attn(3840,'relu')
		self.self_expressive = Self_Expressive(self.batch_size, input_shape=(batch_size, batch_size))
		self.z_conv = None
		self.z_se = None
		self.decoder = Sequential([
			layers.Reshape((16, 16, 15), trainable=False),
			layers.Conv2DTranspose(1, kernel_size=3,
								   activation='relu',
								   # input_shape=input_shape,
								   strides=2,
								   padding='SAME',
								   kernel_initializer = tf.keras.initializers.GlorotUniform(),
								   kernel_regularizer=tf.keras.regularizers.l1())
		])

	def call(self, x):
		z = self.encoder(x)
		z = tf.reshape(z, [self.batch_size, 3840])	# ??????batch????????????
		self.z_conv = z
		# print(z)
		z = self.self_attention(z)
		z = self.self_expressive(z)
		self.z_se = z									# self_expressive_z = theta*z
		# print("z_se:", z.shape)
		z = tf.reshape(z, [self.batch_size, 1, 3840])
		x = self.decoder(z)

		return x

class Mnist_ConvAE(Model):
	def __init__(self, input_shape, batch_size, learning_rate=1e-3):
		super(Mnist_ConvAE, self).__init__()

		self.batch_size = batch_size
		# self.input_img = layers.Input(shape=input_shape)
		self.learning_rate = learning_rate
		# COIL-20??????????????????????????????
		self.encoder = Sequential([
			layers.Conv2D(20, kernel_size=5,
						  activation='relu',
						  input_shape=input_shape[1:],
						  strides=2,
						  padding='SAME',
						  kernel_initializer = tf.keras.initializers.GlorotUniform()),
			layers.Conv2D(10, kernel_size=3,
						  activation='relu',
						  strides=2,
						  padding='SAME',
						  kernel_initializer = tf.keras.initializers.GlorotUniform()),
			layers.Conv2D(5, kernel_size=3,
						  activation='relu',
						  strides=2,
						  padding='SAME',
						  kernel_initializer = tf.keras.initializers.GlorotUniform()),
			layers.Reshape((-1, 80), trainable=False)
		])
		self.self_attention = Self_Attn(80,'relu')
		self.self_expressive = Self_Expressive(self.batch_size, input_shape=(batch_size, batch_size))
		self.z_conv = None
		self.z_se = None
		self.decoder = Sequential([
			layers.Reshape((4, 4, 5), trainable=False),
			layers.Conv2DTranspose(10, kernel_size=3,
								   activation='relu',
								   strides=2,
								   padding='SAME',
								   output_padding=0,
								   kernel_initializer = tf.keras.initializers.GlorotUniform()),
			layers.Conv2DTranspose(20, kernel_size=3,
								   activation='relu',
								   strides=2,
								   padding='SAME',
								   output_padding=1,
								   kernel_initializer = tf.keras.initializers.GlorotUniform()),
			layers.Conv2DTranspose(1, kernel_size=5,
								   activation='relu',
								   strides=2,
								   padding='SAME',
								   output_padding=1,
								   kernel_initializer = tf.keras.initializers.GlorotUniform())
		])

	def call(self, x):
		z = self.encoder(x)
		z = tf.reshape(z, [self.batch_size, -1])	# ??????batch????????????
		self.z_conv = z
		z = self.self_attention(z)
		z = self.self_expressive(z)
		self.z_se = z									# self_expressive_z = theta*z
		# print("z_se:", z.shape)
		z = tf.reshape(z, [self.batch_size, 1, -1])
		x = self.decoder(z)

		return x

class DASC(object):
	def __init__(self, model, input_shape, batch_size=1440, kcluster=20, r=30):
		super(DASC, self).__init__()
		self.kcluster = kcluster
		self.batch_size = batch_size
		# self.conv_ae = ConvAE(batch_size=batch_size, input_shape=input_shape)
		self.conv_ae = model(batch_size=batch_size, input_shape=input_shape)
		self.conv_ae.build(input_shape=input_shape.astype(np.int32)
		self._U = []	# ??????cluster?????????U Projection layer
		self.u_matrix = []

		self.r = r
		# self._m = []	# ??????cluster?????????????????????????????????
		# self._z = []

	def call(self, x):
		# self.G(x, alpha=self.alpha)
		# real_z, fake_z = self.G(x, alpha=self.alpha)
		# self.D(real_z, fake_z, self.r)
		pass

	def initialize(self, train_data, pre_train_epoch=10, learning_rate=1e-3, lambda2=15, lambda3=1):
		'''
		pre-train generator G without considering D
		:param x:
		:return:
		'''

		variables = self.conv_ae.trainable_variables
		optimizer = tf.optimizers.Adam(lr=learning_rate)
		print(self.conv_ae.summary())
		print("Pretraining model...")
		for epoch in range(pre_train_epoch):
			for (batch, (x_batch, y_batch)) in enumerate(train_data):
				with tf.GradientTape() as tape:
					x_reconst = self.conv_ae(x_batch)
					z_conv = self.conv_ae.z_conv
					z_se = self.conv_ae.z_se
					theta = self.conv_ae.layers[1].get_weights()[0]
					# print(x_reconst.dtype, x_r_batch.dtype)
					rec_loss, reconst_loss, self_expr_loss, penalty = loss.ae_loss(x_batch, x_reconst, z_conv, z_se, theta, lambda2=lambda2, lambda3=lambda3)
				grads = tape.gradient(rec_loss, variables)
				optimizer.apply_gradients(zip(grads, variables))

			print("Epoch[{}/{}]: loss={}\treconst_loss={}\tself_expr_loss={}\tpenalty={}".format(
				str(epoch+1), str(pre_train_epoch), str(float(rec_loss)), str(reconst_loss.numpy()), str(self_expr_loss.numpy()), str(penalty.numpy().ravel()[0])))

		if not os.path.exists('pretrain'):
			os.makedirs('pretrain')
		self.conv_ae.save_weights('pretrain/pre_conv_ae.h5')

	def G(self, x, alpha=0.8):
		'''
		Cluster Generator
		:param theta: 	Self-Expressive Coefficient Matrix
		:param z_conv:	Representation
		:return:		Generated vectors
		'''
		x_reconst = self.conv_ae(x)
		z_conv = self.conv_ae.z_conv
		# print(z_conv.shape)
		z_se = self.conv_ae.z_se
		theta = self.conv_ae.layers[1].get_weights()[0]
		theta = np.reshape(theta, [self.batch_size, self.batch_size])

		# normalize theta
		# theta = utils.theta_normalize(theta)
		affinity = 0.5*(np.abs(theta) + np.abs(theta.T))

		# ????????????????????????????????????????????????kernel?????????
		# affinity = np.abs(affinity)
		# Spectral Clustering(N-Cut)
		sc = SpectralClustering(n_clusters=self.kcluster, affinity='precomputed', n_init=100, eigen_solver='arpack', assign_labels='kmeans')
		sc.fit(affinity)
		label_pred = sc.fit_predict(affinity)

		cidx = []
		real_z = []
		# label = []
		fake_z = []
		z_conv = tf.transpose(z_conv)

		# generate fake data
		for k in range(self.kcluster):
			idx = np.where(label_pred == k)[0].tolist()
			cidx.append(idx)
			basis = tf.gather(z_conv, axis=1, indices=idx)
			# print(basis.shape)
			# basis = tf.transpose(basis)
			real_z.append(basis)
			m_k = len(idx)						# num of samples in cluster Ck
			m_fake = math.ceil(m_k * alpha)		# num of generated samples
			# ????????????
			z_k = utils.generate_data(basis, m_k, m_fake)
			fake_z.append(z_k)

		return real_z, fake_z

	def D(self, real_z, fake_z, r):
		'''

		:param clusters: G??????????????????
		:param Z: fake samples generated from G
		:return:
		'''
		_U = []		# Ui ??????
		u_matrix = []
		selected_z = []
		for k in range(self.kcluster):
			# index = np.arange(real_z[k].shape[1])
			# np.random.shuffle(index)
			# z = tf.gather(real_z[k], axis=1, indices=index)

			# QR decomposition: get U_i
			U_raw, other = qr(real_z[k], mode='full')
			u_k = 0
			min_pr = 99999
			index = np.arange(U_raw.shape[1])
			# for i in range(10):
			# 	np.random.shuffle(index)
			# 	U = tf.gather(U_raw, axis=1, indices=index[0:r])
			# 	# U = U[:, 0:r]
			# 	u = Projection(U, input_shape=real_z[k].shape, name="candidate_".format(str(k)))
			# 	u.build(real_z[k].shape)
			# 	# calculate projection residuals
			# 	proj = u(real_z[k])
			# 	l = tf.reduce_mean(loss.projection_residual(real_z[k], proj))
			# 	if l < min_pr:
			# 		min_pr = l
			# 		u_k = u

			U = U_raw[:, 0:r]
			# # Lr_z = loss.projection_residual(_z, U)
			# # print(U.shape)
			u_k = Projection(U, input_shape=real_z[k].shape, name="U{}".format(str(k)))
			u_k.build(real_z[k].shape)

			_U.append(u_k)

		self._U = _U


	def forward(self, z):
		proj = [i for i in range(self.kcluster)]
		for k in range(self.kcluster):
			# z = np.hstack([real_z[k], fake_z[k]])
			p = self._U[k](z[k])
			# print(k, p.shape)
			proj[k] = p

		return proj


