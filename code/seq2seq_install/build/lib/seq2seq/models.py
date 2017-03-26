from __future__ import absolute_import
from recurrentshop import LSTMCell, RecurrentContainer
from .cells import LSTMDecoderCell, AttentionDecoderCell
from keras.models import Sequential, Model
from keras.layers import Dense, Dropout, TimeDistributed, Bidirectional, Input, Lambda
from keras.layers.embeddings import Embedding
from keras.objectives import mean_squared_error
import keras.backend as K
import tensorflow as tf


'''
Papers:
[1] Sequence to Sequence Learning with Neural Networks (http://arxiv.org/abs/1409.3215)
[2] Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation (http://arxiv.org/abs/1406.1078)
[3] Neural Machine Translation by Jointly Learning to Align and Translate (http://arxiv.org/abs/1409.0473)
'''


def SimpleSeq2Seq(output_dim, output_length, latent_dim, batch_size, epsilon_std, 
	                    lookup_matrix=None, hidden_dim=None, depth=1, dropout=0., **kwargs):
    '''
    Simple model for sequence to sequence learning.
    The encoder encodes the input sequence to vector (called context vector)
    The decoder decodes the context vector in to a sequence of vectors.
    There is no one on one relation between the input and output sequence elements.
    The input sequence and output sequence may differ in length.

    Arguments:

    output_dim : Required output dimension.
    hidden_dim : The dimension of the internal representations of the model.
    output_length : Length of the required output sequence.
    depth : Used to create a deep Seq2seq model. For example, if depth = 3, 
            there will be 3 LSTMs on the enoding side and 3 LSTMs on the 
            decoding side. You can also specify depth as a tuple. For example,
            if depth = (4, 5), 4 LSTMs will be added to the encoding side and
            5 LSTMs will be added to the decoding side.
    dropout : Dropout probability in between layers.

    '''
    if type(depth) == int:
        depth = [depth, depth]
    if 'batch_input_shape' in kwargs:
        shape = kwargs['batch_input_shape']
        del kwargs['batch_input_shape']
    elif 'input_shape' in kwargs:
        shape = (None,) + tuple(kwargs['input_shape'])
        del kwargs['input_shape']
    elif 'input_dim' in kwargs:
        if 'input_length' in kwargs:
            shape = (None, kwargs['input_length'], kwargs['input_dim'])
            del kwargs['input_length']
        else:
            shape = (None, None, kwargs['input_dim'])
        del kwargs['input_dim']
    if 'unroll' in kwargs:
        unroll = kwargs['unroll']
        del kwargs['unroll']
    else:
        unroll = False
    if 'stateful' in kwargs:
        stateful = kwargs['stateful']
        del kwargs['stateful']
    else:
        stateful = False
    if not hidden_dim:
        hidden_dim = output_dim


    embedder = Embedding(input_dim=lookup_matrix.shape[0], output_dim=lookup_matrix.shape[1], \
    	input_length=output_length, weights=[lookup_matrix])
    encoder = RecurrentContainer(unroll=unroll, stateful=stateful, input_length=shape[1])
    encoder.add(LSTMCell(hidden_dim, batch_input_shape=(shape[0], shape[2]), **kwargs))
    for _ in range(1, depth[0]):
        encoder.add(Dropout(dropout))
        encoder.add(LSTMCell(hidden_dim, **kwargs))

    decoder = RecurrentContainer(unroll=unroll, stateful=stateful, decode=True, output_length=output_length, input_length=shape[1])
    decoder.add(Dropout(dropout, batch_input_shape=(shape[0], hidden_dim)))

    if depth[1] == 1:
        decoder.add(LSTMCell(output_dim, **kwargs))
    else:
        decoder.add(LSTMCell(hidden_dim, **kwargs))
        for _ in range(depth[1] - 2):
            decoder.add(Dropout(dropout))
            decoder.add(LSTMCell(hidden_dim, **kwargs))

        decoder.add(Dropout(dropout))
        decoder.add(LSTMCell(output_dim, **kwargs))


    x = Input(batch_shape=(None,output_length))
    embedded_x = embedder(x)

    h_encoded = encoder(embedded_x)

    print h_encoded

    def sampling(args):
        z_mean, z_log_var = args         
        epsilon = K.random_normal(shape=(batch_size, latent_dim), mean=0., std=epsilon_std)
        return z_mean + K.exp(z_log_var / 2) * epsilon

    z_mean = Dense(latent_dim)(h_encoded)
    z_log_var = Dense(latent_dim)(h_encoded)
    z = Lambda(sampling, output_shape=(latent_dim,))([z_mean, z_log_var])
    print z

    h_0 = Dense(hidden_dim, activation='relu')(z)
    print h_0
    model_out = decoder(h_0)
    print model_out

    # model_out = decoder(h_encoded)

    y = Input(batch_shape=(None,output_length))
    embedded_y = embedder(y)
    print embedded_y

    loss = tf.reduce_sum(mean_squared_error(model_out, embedded_y))

    adam = tf.train.AdamOptimizer()
    optimizer = adam.minimize(loss)

    return optimizer, loss, x, y


def Seq2Seq(output_dim, output_length, lookup_matrix, hidden_dim=None, depth=1, broadcast_state=True, inner_broadcast_state=True, teacher_force=False, peek=False, dropout=0., **kwargs):
    '''
    Seq2seq model based on [1] and [2].
    This model has the ability to transfer the encoder hidden state to the decoder's
    hidden state(specified by the broadcast_state argument). Also, in deep models 
    (depth > 1), the hidden state is propogated throughout the LSTM stack(specified by 
    the inner_broadcast_state argument. You can switch between [1] based model and [2] 
    based model using the peek argument.(peek = True for [2], peek = False for [1]).
    When peek = True, the decoder gets a 'peek' at the context vector at every timestep.

    [1] based model:

        Encoder:
        X = Input sequence
        C = LSTM(X); The context vector

        Decoder:
        y(t) = LSTM(s(t-1), y(t-1)); Where s is the hidden state of the LSTM (h and c)
        y(0) = LSTM(s0, C); C is the context vector from the encoder.

    [2] based model:

        Encoder:
        X = Input sequence
        C = LSTM(X); The context vector

        Decoder:
        y(t) = LSTM(s(t-1), y(t-1), C)
        y(0) = LSTM(s0, C, C)
        Where s is the hidden state of the LSTM (h and c), and C is the context vector 
        from the encoder.

    Arguments:

    output_dim : Required output dimension.
    hidden_dim : The dimension of the internal representations of the model.
    output_length : Length of the required output sequence.
    depth : Used to create a deep Seq2seq model. For example, if depth = 3, 
            there will be 3 LSTMs on the enoding side and 3 LSTMs on the 
            decoding side. You can also specify depth as a tuple. For example,
            if depth = (4, 5), 4 LSTMs will be added to the encoding side and
            5 LSTMs will be added to the decoding side.
    broadcast_state : Specifies whether the hidden state from encoder should be 
                      transfered to the deocder.
    inner_broadcast_state : Specifies whether hidden states should be propogated 
                            throughout the LSTM stack in deep models.
    peek : Specifies if the decoder should be able to peek at the context vector
           at every timestep.
    dropout : Dropout probability in between layers.


    '''
    if type(depth) == int:
        depth = [depth, depth]
    if 'batch_input_shape' in kwargs:
        shape = kwargs['batch_input_shape']
        del kwargs['batch_input_shape']
    elif 'input_shape' in kwargs:
        shape = (None,) + tuple(kwargs['input_shape'])
        del kwargs['input_shape']
    elif 'input_dim' in kwargs:
        if 'input_length' in kwargs:
            shape = (None, kwargs['input_length'], kwargs['input_dim'])
            del kwargs['input_length']
        else:
            shape = (None, None, kwargs['input_dim'])
        del kwargs['input_dim']
    if 'unroll' in kwargs:
        unroll = kwargs['unroll']
        del kwargs['unroll']
    else:
        unroll = False
    if 'stateful' in kwargs:
        stateful = kwargs['stateful']
        del kwargs['stateful']
    else:
        stateful = False
    if not hidden_dim:
        hidden_dim = output_dim

    encoder = RecurrentContainer(readout=True, state_sync=inner_broadcast_state, input_length=shape[1], unroll=unroll, stateful=stateful, return_states=broadcast_state)
    for i in range(depth[0]):
        encoder.add(LSTMCell(hidden_dim, batch_input_shape=(shape[0], hidden_dim), **kwargs))
        encoder.add(Dropout(dropout))
    dense1 = TimeDistributed(Dense(hidden_dim))
    dense1.supports_masking = True
    dense2 = Dense(output_dim)

    decoder = RecurrentContainer(readout='add' if peek else 'readout_only', state_sync=inner_broadcast_state, output_length=output_length, unroll=unroll, stateful=stateful, decode=True, input_length=shape[1])
    for i in range(depth[1]):
        decoder.add(Dropout(dropout, batch_input_shape=(shape[0], output_dim)))
        decoder.add(LSTMDecoderCell(output_dim=output_dim, hidden_dim=hidden_dim, batch_input_shape=(shape[0], output_dim), **kwargs))

    input = Input(batch_shape=(shape[0],shape[1]))
    print input.shape
    embedded_input = Embedding(input_dim=lookup_matrix.shape[0], output_dim=lookup_matrix.shape[1], weights=[lookup_matrix])(input)
    print embedded_input.shape
    input._keras_history[0].supports_masking = True

    encoded_seq = dense1(embedded_input)
    # print encoded_seq.shape
    encoded_seq = encoder(encoded_seq)
    print encoded_seq

    if broadcast_state:
        states = encoded_seq[-2:]
        encoded_seq = encoded_seq[0]
    else:
        states = [None] * 2
    encoded_seq = dense2(encoded_seq)
    inputs = [input]
    if teacher_force:
        truth_tensor = Input(batch_shape=(shape[0], output_length, output_dim))
        truth_tensor._keras_history[0].supports_masking = True
        inputs += [truth_tensor]
    decoded_seq = decoder({'input': encoded_seq, 'ground_truth': inputs[1] if teacher_force else None, 'initial_readout': encoded_seq, 'states': states})

    model = Model(inputs, decoded_seq)
    model.encoder = encoder
    model.decoder = decoder

    print "==========Input========="
    print model.input
    print "==========Input========="
    print model.output

    return model


def AttentionSeq2Seq(output_dim, output_length, hidden_dim=None, depth=1, bidirectional=True, dropout=0., **kwargs):
    '''
    This is an attention Seq2seq model based on [3].
    Here, there is a soft allignment between the input and output sequence elements.
    A bidirection encoder is used by default. There is no hidden state transfer in this
    model.

    The  math:

        Encoder:
        X = Input Sequence of length m.
        H = Bidirection_LSTM(X); Note that here the LSTM has return_sequences = True, 
        so H is a sequence of vectors of length m.

        Decoder:
        y(i) = LSTM(s(i-1), y(i-1), v(i)); Where s is the hidden state of the LSTM (h and c)
        and v (called the context vector) is a weighted sum over H:

        v(i) =  sigma(j = 0 to m-1)  alpha(i, j) * H(j)

        The weight alpha[i, j] for each hj is computed as follows:
        energy = a(s(i-1), H(j))        
        alhpa = softmax(energy)
        Where a is a feed forward network.

    '''
    if type(depth) == int:
        depth = [depth, depth]
    if 'batch_input_shape' in kwargs:
        shape = kwargs['batch_input_shape']
        del kwargs['batch_input_shape']
    elif 'input_shape' in kwargs:
        shape = (None,) + tuple(kwargs['input_shape'])
        del kwargs['input_shape']
    elif 'input_dim' in kwargs:
        if 'input_length' in kwargs:
            shape = (None, kwargs['input_length'], kwargs['input_dim'])
            del kwargs['input_length']
        else:
            shape = (None, None, kwargs['input_dim'])
        del kwargs['input_dim']
    if 'unroll' in kwargs:
        unroll = kwargs['unroll']
        del kwargs['unroll']
    else:
        unroll = False
    if 'stateful' in kwargs:
        stateful = kwargs['stateful']
        del kwargs['stateful']
    else:
        stateful = False
    if not hidden_dim:
        hidden_dim = output_dim
    encoder = RecurrentContainer(unroll=unroll, stateful=stateful, return_sequences=True, input_length=shape[1])
    encoder.add(LSTMCell(hidden_dim, batch_input_shape=(shape[0], shape[2]), **kwargs))
    for _ in range(1, depth[0]):
        encoder.add(Dropout(dropout))
        encoder.add(LSTMCell(hidden_dim, **kwargs))
    input = Input(batch_shape=shape)
    input._keras_history[0].supports_masking = True
    if bidirectional:
        encoder = Bidirectional(encoder, merge_mode='sum')
    encoded = encoder(input)

    decoder = RecurrentContainer(decode=True, output_length=output_length, unroll=unroll, stateful=stateful, input_length=shape[1])
    decoder.add(Dropout(dropout, batch_input_shape=(shape[0], shape[1], hidden_dim)))
    if depth[1] == 1:
        decoder.add(AttentionDecoderCell(output_dim=output_dim, hidden_dim=hidden_dim))
    else:
        decoder.add(AttentionDecoderCell(output_dim=hidden_dim, hidden_dim=hidden_dim))
        for _ in range(depth[1] - 2):
            decoder.add(Dropout(dropout))
            decoder.add(LSTMDecoderCell(output_dim=hidden_dim, hidden_dim=hidden_dim))
        decoder.add(Dropout(dropout))
        decoder.add(LSTMDecoderCell(output_dim=output_dim, hidden_dim=hidden_dim))
    inputs = [input]
    '''
    if teacher_force:
        truth_tensor = Input(batch_shape=(shape[0], output_length, output_dim))
        inputs += [truth_tensor]
        decoder.set_truth_tensor(truth_tensor)
    '''
    decoded = decoder(encoded)
    model = Model(inputs, decoded)
    return model