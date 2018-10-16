FROM ocaml/opam2:ubuntu-18.04
MAINTAINER Adrian Sampson <asampson@cs.cornell.edu>

# Add Python, pipenv, and node for buildbot.
RUN sudo apt-get install -y software-properties-common && \
    sudo add-apt-repository ppa:deadsnakes/ppa && \
    curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | sudo apt-key add - && \
    sudo apt-add-repository \
        'deb https://dl.yarnpkg.com/debian/ stable main' && \
    sudo apt-get update
RUN sudo apt-get install -y python3.7 nodejs yarn
RUN curl https://bootstrap.pypa.io/get-pip.py | sudo -H python3.7
ENV PATH ${HOME}/.local/bin:${PATH}
RUN pip install --user pipenv

# Install some of our OCaml dependencies.
RUN opam config exec -- opam depext --install -y \
    dune menhir core ppx_deriving ppx_expect cmdliner
    
# Install sshpass
RUN sudo apt-get install sshpass
RUN sudo chown opam:opam ~/.ssh
#RUN sudo chown opam:opam ~/.ssh/*

# Add opam bin directory to our $PATH so we can run seac.
ENV PATH ${HOME}/.opam/system/bin:${PATH}

# Volume, port, and command for buildbot.
VOLUME ${HOME}/seashell/buildbot/instance
EXPOSE 8000
ENV PIPENV_PIPFILE=buildbot/Pipfile
CMD ["pipenv", "run", \
     "gunicorn", "--bind", "0.0.0.0:8000", "--chdir", "buildbot", \
     "buildbot.server:app"]

# Add Seashell source.
WORKDIR ${HOME}
ADD --chown=opam . seashell
WORKDIR seashell

# Build Seashell.
RUN opam install --deps-only .
RUN eval `opam config env` ; dune build
RUN eval `opam config env` ; dune install

# Avoids a bug in a recent version of pip:
# https://github.com/pypa/pipenv/issues/2924
RUN sudo pip install pip==18.0
RUN cd buildbot ; PIPENV_PIPFILE= pipenv run pip install pip==18.0

# Set up buildbot.
RUN cd buildbot ; PIPENV_PIPFILE= pipenv install
RUN cd buildbot ; yarn
RUN cd buildbot ; yarn build
