"""
Implements a simple stacked autoencoder.

Hyperparameters to tune:
------------------------
- Learning rate
- Activation function (sigmoid, ReLU, atan)
- Amount of neurons in each layer
- Learning function (GradientDescentOptimizer, RMSProp, AdamOptimizer)
- Batch size
"""
import numpy as np
import tensorflow as tf

from sys import stdout, path
from os import path as ospath

path.append(ospath.dirname(ospath.dirname(ospath.abspath(__file__))))
import helpers

class AutoEncoder():
    """
    Implements an autoencoder that tries to learn a representation for web page traces.

    Atrributes:
        - activation_func is a tensorflow function, representing the activation function used.
            *(Often found in `tf.nn`)*
        - encoder is a computation, representing the encoder layers
        - decoder is another computtational graph, representing the decoder layers
        - loss is the operation for the mean squared error (MSE)
        - train_op is the train operation (`RMSProp`)
        - layers is a list of integerrs, determining the amount of layers and their size
        - batch_size
        - learning_rate
    """

    def __init__(self, layers, batch_size, activation_func=tf.nn.sigmoid, saved_graph=None, sess=None, learning_rate=0.0001):
        """
        @param layers is a list of integers, determining the amount of layers and their size
            starting with the input size
        """
        if len(layers) < 2:
            print("Amount of layers must be greater than 1")
            exit(0)

        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.activation_func = activation_func

        # Use this in data preprocessing
        self.layers = layers

        self._make_graph(layers)

        if saved_graph is not None and sess is not None:
            self.import_from_file(sess, saved_graph)

    def _make_graph(self, layers):
        """
        Constructs the computational graph

        @param layers is a list of integers, determining the size of the layers
        """
        self._init_placeholders(layers[0])

        self.encoder = self._init_encoder(layers)
        self.decoder = self._init_decoder(layers)

        self._init_train()

    def _init_placeholders(self, first_layer):
        """
        The main placeholders for input and output data
        """
        self.encoder_inputs = tf.placeholder(tf.float32, [self.batch_size, first_layer])

        # We could technically use the same value as encoder_inputs but we do not
        # for future possible extensions
        self.decoder_targets = tf.placeholder(tf.float32, [self.batch_size, first_layer])


    def _init_encoder(self, layers):
        """
        Creates the layers of the decoder and returns the last layer.
        """
        previous_layer = None

        # We don't want to enumerate over the last one
        for i in range(len(layers) - 1):
            weight = tf.Variable(tf.random_normal([layers[i], layers[i + 1]]))
            bias = tf.Variable(tf.random_normal([layers[i + 1]]))

            current_layer = None
            if previous_layer is None:
                current_layer = self.activation_func(tf.add(tf.matmul(self.encoder_inputs, weight), bias))
            else:
                current_layer = self.activation_func(tf.add(tf.matmul(previous_layer, weight), bias))

            previous_layer = current_layer

        # Will be the last layer
        return previous_layer

    def _init_decoder(self, layers):
        """
        Creates the decoder graph and returns the last layer
        """
        previous_layer = None

        # We don't want to enumerate over the last one
        for i in range(len(layers) - 1, 0, -1):
            weight = tf.Variable(tf.random_normal([layers[i], layers[i - 1]]))
            bias = tf.Variable(tf.random_normal([layers[i - 1]]))

            current_layer = None
            if previous_layer is None:
                current_layer = self.activation_func(tf.add(tf.matmul(self.encoder, weight), bias))
            else:
                current_layer = self.activation_func(tf.add(tf.matmul(previous_layer, weight), bias))

            previous_layer = current_layer

        # Will be the last layer
        return previous_layer

    def _init_train(self):
        """
        Create the train operation
        """
        self.loss = tf.reduce_sum(tf.square(self.decoder_targets - self.decoder))

        # Which optimizer to use? `GradientDescentOptimizer`, `AdamOptimizer` or `RMSProp`?
        self.train_op = tf.train.AdamOptimizer(self.learning_rate).minimize(self.loss)

    def _get_cumulative_representation(self, trace, n):
        """
        Gets a cumulative representation of a trace, described in the "Website Fingerprinting at Internet Scale" paper.

        @param n is the amount of features to be added.
            It affects how often and the places where you sample

        @return a fixed-length list of features (`len(features) == n`)
        """
        features = []

        a, c = 0, 0

        sample = (len(trace) // n)
        sample = 1 if sample == 0 else sample
        amount = 0

        for i, packet in enumerate(trace):
            c += packet[1]
            a += abs(packet[1])

            if i % sample == 0:
                amount += 1
                features.append(c + a)

                if amount == n:
                    break

        for i in range(amount, n):
            features.append(0)

        return features


    def next_batch(self, batches, in_memory):
        """
        Returns the next batch in some fixed-length representation.
        Currently we use Panchenko et al.'s cumulative traces

        @param batches an iterator with all of the batches (
            if in_memory == True:
                in batch-major form without padding
            else:
                A list of paths to the files
        )
        @param in_memory is a boolean value

        @return if in_memory is False, returns a tuple of (dict, [paths]) where paths is a list of paths for each batch
            else it returns a dict for training
        """
        batch = next(batches)
        data_batch = batch

        if not in_memory:
            data_batch = [helpers.read_cell_file(path) for path in batch]

        data_batch = [self._get_cumulative_representation(trace, self.layers[0]) for trace in data_batch]

        encoder_inputs_ = data_batch
        decoder_targets_ = data_batch

        train_dict = {
            self.encoder_inputs: encoder_inputs_,
            self.decoder_targets: decoder_targets_,
        }

        if not in_memory:
            return (train_dict, batch)
        return train_dict

    def save(self, sess, file_name):
        """
        Save the model in a file

        @param sess is the session
        @param file_name is the file name without the extension
        """
        saver = tf.train.Saver()
        saver.save(sess, file_name)

    def import_from_file(self, sess, file_name):
        """
        Imports the graph from a file

        @param sess is the session
        @param file_name is a string that represents the file name
            without the extension
        """

        # Get the graph
        saver = tf.train.Saver()

        # Restore the variables
        saver.restore(sess, file_name)



def train_on_copy_task(sess, model, data,
                       batch_size=100,
                       max_batches=None,
                       batches_in_epoch=1000,
                       verbose=False):
    """
    Train the `AutoEncoder` on a copy task

    @param sess is a tensorflow session
    @param model is the autoencoder model
    @param data is the data (in batch-major form and not padded or a list of files (depending on `in_memory`))
    """
    batches = helpers.get_batches(data, batch_size=batch_size)

    loss_track = []

    batches_in_data = len(data) // batch_size
    if max_batches is None or batches_in_data < max_batches:
        max_batches = batches_in_data - 1

    try:
        for batch in range(max_batches):
            print("Batch {}/{}".format(batch, max_batches))
            fd, _ = model.next_batch(batches, False)
            _, l = sess.run([model.train_op, model.loss], fd)

            loss_track.append(l)

            if batch == 0 or batch % batches_in_epoch == 0:
                model.save(sess, 'autoencoder_model')
                helpers.save_object(loss_track, 'loss_track.pkl')

                if verbose:
                    stdout.write('  minibatch loss: {}\n'.format(sess.run(model.loss, fd)))
                    predict_ = sess.run(model.decoder_outputs, fd)
                    for i, (inp, pred) in enumerate(zip(fd[model.encoder_inputs].swapaxes(0, 1), predict_.swapaxes(0, 1))):
                        stdout.write('  sample {}:\n'.format(i + 1))
                        stdout.write('    input     > {}\n'.format(inp))
                        stdout.write('    predicted > {}\n'.format(pred))
                        if i >= 0:
                            break
                    stdout.write('\n')

    except KeyboardInterrupt:
        stdout.write('training interrupted')
        model.save(sess, 'autoencoder_model')
        exit(0)

    model.save(sess, 'autoencoder_model')
    helpers.save_object(loss_track, 'loss_track.pkl')

    return loss_track

def get_vector_representations(sess, model, data, save_dir,
                       batch_size=100,
                       max_batches=None,
                       batches_in_epoch=1000,
                       extension=".cell"):
    """
    Given a trained model, gets a vector representation for the traces in batch

    @param sess is a tensorflow session
    @param model is the autoencoder model
    @param data is the data (in batch-major form and not padded or a list of files (depending on `in_memory`))
    """
    batches = helpers.get_batches(data, batch_size=batch_size)

    batches_in_data = len(data) // batch_size
    if max_batches is None or batches_in_data < max_batches:
        max_batches = batches_in_data - 1

    try:
        for batch in range(max_batches):
            print("Batch {}/{}".format(batch, max_batches))
            fd, paths = model.next_batch(batches, False)
            l = sess.run(model.encoder, fd)

            file_names = [helpers.extract_filename_from_path(path, extension) for path in paths]

            for file_name, features in zip(file_names, list(l)):
                helpers.write_to_file(features, save_dir, file_name, new_extension=".cellf")

    except KeyboardInterrupt:
        stdout.write('Interrupted')
        exit(0)

    return results