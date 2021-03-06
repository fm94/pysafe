import itertools
from sklearn.neighbors import KDTree
import numpy as np
from sklearn.model_selection import train_test_split
from evolutionary_search import maximize
from tqdm import tqdm

class SAFE():
    """per SAmple Feature Elimination
    """

    def __init__(self, combinations_mode='all', n_combinations=10, n_points=None, random_state=None):
        """Initiate a SAFE model.

        Args:
            combinations_mode (str, optional): 
                'forward selection': Generate the combination vector based
                of the forward selection algorithm,
                'all': generate all possible combinations,
                'one-by-one': cancle out one features at a time,
                'random': generate all possible combinations. Defaults to 'all'.
            n_combinations (int, optional): Limit the number of combinations
            by selecting a subset. Defaults to 10.
            n_points ([type], optional): Limit the number of data samples
            to enable faster scanning. Defaults to None.
            random_state ([type], optional): Random state of the model.
            Defaults to None.
        """

        self.n_features = None
        self.combinations_mode = combinations_mode
        self.algorithm = None
        self.combinations = None
        self.tree = None
        self.X = None
        self.y_better = None
        self.y_worst = None
        self.y = None
        self.aim = None
        self.model = None
        self.n_points = n_points
        self.random_state = random_state
        self.n_combinations = n_combinations
        self.tree = None
        self.learner = None

    def scan(self, model, X, y, aim='worst'):
        """Scan a Keras model.

        Args:
            model (keras model): Keras model to be scanned
            X (numpy nd-array): Input Data for scanning
            y (numpy array): Input Labels for scanning
            aim (str, optional): If 'worst' is chosen, SAFE learns 
            to generate adversarial samples. If 'better' is chosen,
            SAFE learns to improve accuracy. Defaults to 'worst'.
        """

        if not isinstance(X,np.ndarray):
            X = X.values
        if not isinstance(y,np.ndarray):
            y = y.values
        
        [rows, self.n_features] = X.shape

        if self.n_points is not None:
            X, _, y, _ = train_test_split(X, y, train_size=self.n_points/rows, random_state=self.random_state, stratify=y)
        
        self.X = X
        self.y_better = np.zeros((rows, self.n_features))
        self.y_worst = np.zeros((rows, self.n_features))
        self._generate_combination()
        self.model = model
        self.aim = aim
        
        # TODO migrate this also
        if self.combinations_mode == 'genetic':
            param_grid = {'combination': self.combinations}
            for i,j in enumerate(tqdm(X)):
                args = {'data': j, 'label':y_train.values[i]}
                best_params, _, _, _, _ = maximize(self.__combination_search_genetic, param_grid, args, verbose=False)
                self.X_train_fs[i,:] = j
                self.y_train_fs[i,:] = best_params['combination']
                
        elif self.combinations_mode == 'forward_selection':
            if self.aim == 'better':
                for i,j in enumerate(tqdm(self.X)):
                    self.y_better[i,:] = self.__combination_search_forward_selection_min(j, y[i])
            else:
                for i,j in enumerate(tqdm(self.X)):
                    self.y_worst[i,:] = self.__combination_search_forward_selection_max(j, y[i])
        else:
            losses = np.zeros((rows, self.combinations.shape[0]))
            for index, p in enumerate(tqdm(self.combinations)):
                losses[:, index] = abs(self.model.predict(np.multiply(p, self.X)).flatten() - y)
        
            self.y_worst = self.combinations[losses.argmax(axis=1)]
            self.y_better = self.combinations[losses.argmin(axis=1)]
        
    def learn(self, algorithm='knn', aim='worst', learner=None, train=False):
        """Learn the set of combinations with a SAFE Model.
        This will generate a second model that is able
        to learn the selection.

        Args:
            algorithm (str, optional): Algorithm to use for the learning
            process. 'knn' or 'ann'. Defaults to 'knn'.
            aim (str, optional): If 'worst' is chosen, SAFE learns 
            to generate adversarial samples. If 'better' is chosen,
            SAFE learns to improve accuracy. Defaults to 'worst'.
            If already selected in learn(), skip it here.
            learner (sklearn KDtree or Keras model, optional): 
            an external model can be passed. Defaults to None.
            train (bool, optional): If an external model is passed
            and is not pre-trained, it can be trained also. Defaults to False.

        Returns:
            sklearn KDtree or Keras model: SAFE Model that can generate combiantions 
            from data sampeles.
        """

        self.aim = aim if not self.aim else self.aim
        self.y = self.y_better if self.aim == 'better' else self.y_worst
        self.algorithm = algorithm
        self.learner = learner if learner else None
        
        if self.algorithm == 'knn':
            if not learner:
                self.learner = KDTree(self.X)
        if self.algorithm == 'ann':
            self._ann(train)
        return self.learner

    def get_selection(self, data):
        """Get the binary selection of features given a dataset.

        Args:
            data (numpy nd-array): Data to get the selection for.

        Returns:
            nd-array: Binary selection array.
        """

        if self.algorithm == 'knn':
            _, ind = self.learner.query(data, k=1)
            return self.y[ind.flatten()]
        if self.algorithm == 'ann':
            return self.learner.predict(data).round()

    def get_robustness(self, data=None):
        """Robustness score per feature.

        Args:
            data (nd-array, optional): If Data is passed, returns the robustness
            of that data otherwise returns the robustness of the data
            used during scanning. Defaults to None.

        Returns:
            [numpy array]: per-feature robustness score
        """

        if data is not None:
            y = self.get_selection(data)
            mean = np.mean(y, 0)
            return {'robustness': mean/np.sum(mean)*100}
        else:
            mean1 = np.mean(self.y_better, 0)
            mean2 = np.mean(self.y_worst, 0)
            return {'robustness_better': mean1/np.sum(mean1)*100,
                    'robustness_worst': mean2/np.sum(mean2)*100}

    def _generate_combination(self):

        if self.combinations_mode == 'all' or self.combinations_mode == 'genetic':
            self.combinations =  np.flip(np.array(list(itertools.product([0, 1], repeat=self.n_features))))
        if self.combinations_mode == 'one-by-one':
            self.combinations = np.ones((self.n_features+1, self.n_features))
            for i in range(1, self.n_features):
                self.combinations[i,i] = 0
        if self.combinations_mode == 'random':
            self.combinations = np.array(list(itertools.product([0, 1], repeat=self.n_features)))
            self.combinations =  random.sample(self.combinations, min(self.n_combinations, len(self.combinations)))

    def clean_data(self, data):
        """Clean a given Dataset by replacing irrelevant
        features by 0 depeding on the aim.

        Args:
            data (numpy nd-array): Data to be cleaned.

        Returns:
            [type]: [description]
        """

        return np.multiply(data, self.get_selection(data))

    def __combination_search_genetic(self, combination, data, label):
        sample = np.multiply(data, combination)
        return 1/(sum(abs(self.model.predict(np.array([sample,]))[0] - label)))
    
    def __combination_search_forward_selection_min(self, data, label):
        # Duplicate code for faster operation

        best_combination = np.ones(self.n_features)
        best_loss = abs(self.model.predict(np.array([np.multiply(data, best_combination)])) - label)
        for _ in range(self.n_features):
            combinations = []
            losses = []
            for i in range(self.n_features):
                current_combination = best_combination.copy()
                if current_combination[i] != 0:
                    current_combination[i] = 0
                    combinations.append(current_combination)
                    losses.append(abs(self.model.predict(np.array([np.multiply(data, current_combination)])) - label))
            current_loss = min(losses)
            #print('best loss {} best combination {} | current loss {} current combination {}'.format(best_loss, best_combination, current_loss, current_combination))
            if current_loss < best_loss:
                best_combination = combinations[losses.index(current_loss)]
                best_loss = current_loss
            else:
                return best_combination
        return best_combination
            
    def __combination_search_forward_selection_max(self, data, label):
        # Duplicate code for faster operation

        best_combination = np.ones(self.n_features)
        best_loss = abs(self.model.predict(np.array([np.multiply(data, best_combination)])) - label)
        for _ in range(self.n_features):
            combinations = []
            losses = []
            for i in range(self.n_features):
                current_combination = best_combination.copy()
                if current_combination[i] != 0:
                    current_combination[i] = 0
                    combinations.append(current_combination)
                    losses.append(abs(self.model.predict(np.array([np.multiply(data, current_combination)])) - label))
            current_loss = max(losses)
            #print('best loss {} best combination {} | current loss {} current combination {}'.format(best_loss, best_combination, current_loss, current_combination))
            if current_loss > best_loss:
                best_combination = combinations[losses.index(current_loss)]
                best_loss = current_loss
            else:
                return best_combination
        return best_combination
            
    def _ann(self, train):

        if not self.learner:
            self.learner = Sequential()
            self.learner.add(Dense(64, input_dim=self.n_features, activation='relu'))
            self.learner.add(Dense(64, activation='relu'))
            self.learner.add(Dense(64, activation='relu'))
            self.learner.add(Dense(self.n_features, activation='sigmoid'))
            self.learner.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])
            self.learner.fit(self.X, self.y, epochs=2, batch_size=16)
            return
        
        if train:
            self.learner.fit(self.X, self.y, epochs=128, batch_size=8)
        
    def _get_clean(self, data):

        return self.model.predict_classes(data), self.model.predict_classes(self.clean_data(data))
    
    def get_accuracy(self, data, labels):
        """Get the accuracy of a given model before and after 
        applying SAFE to a dataset.

        Args:
            data (numpy nd-array): Dataset.
            labels (numpy nd-array): Labels.
        """

        original_predictions, cleaned_predictions = self._get_clean(data)
        
        # TODO: fix exception workround
        # handle multiclass
        try:
            print('Accuracy before: {}'.format(accuracy_score(np.argmax(labels, 1), original_predictions)))
            print('Accuracy after: {}'.format(accuracy_score(np.argmax(labels, 1), cleaned_predictions)))
        # handle binary
        except:
            print('Accuracy before: {}'.format(accuracy_score(labels, original_predictions)))
            print('Accuracy after: {}'.format(accuracy_score(labels, cleaned_predictions)))
        
    def get_behaviour(self, data):
        """Get the prediction of a data sample / dataset
        before and after applying SAFE.

        Args:
            data (numpy nd-array): Data sample or set to be analyzed.

        Returns:
            numpy array: Prediction before and prediction after values.
        """

        return self.model.predict(data), self.model.predict(self.clean_data(data))
    
    def get_candidates(self, data, threshold=0.9):
        """Get samples that can be candidates depeding
        on the aim selected before.

        Args:
            data (numpy nd-array): Input data.
            threshold (float, optional): The minimum change in the prediction to be 
            considered. Defaults to 0.9.

        Returns:
            numpy array: Index of samples that are considered as candidates.
        """

        original_predictions, cleaned_predictions = self.behaviour(data)
        displacement = original_predictions - cleaned_predictions
        return [j for (i,j) in zip(displacement,list(range(len(displacement)))) if i >= threshold] 
