#flywheel/fmriprep

############################
# Get the fmriprep algorithm from DockerHub
FROM poldracklab/fmriprep:1.2.5

MAINTAINER Ted Satterthwaite <sattertt@upenn.edu>

ENV FMRIPREP_VERSION 1.2.5

############################
# Install basic dependencies
RUN apt-get update && apt-get -y install \
    jq \
    tar \
    zip \
    build-essential


############################
# Install the Flywheel SDK
RUN pip install 'flywheel-sdk==6.0.6'
RUN pip install fw-heudiconv
RUN pip install heudiconv

############################
# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
RUN mkdir -p ${FLYWHEEL}
COPY run ${FLYWHEEL}/run
COPY manifest.json ${FLYWHEEL}/manifest.json
COPY fs_license.py /flywheel/v0/fs_license.py

# Set the entrypoint
ENTRYPOINT ["/flywheel/v0/run"]

# Add the fmriprep dockerfile to the container
ADD https://raw.githubusercontent.com/poldracklab/fmriprep/${FMRIPREP_VERSION}/Dockerfile ${FLYWHEEL}/fmriprep_${FMRIPREP_VERSION}_Dockerfile


############################
# Copy over python scripts that generate the BIDS hierarchy
COPY bids-client /bids-client
RUN cd /bids-client \
  && cd /bids-client \
  && pip install .
COPY create_archive_fw_heudiconv.py /flywheel/v0/create_archive_fw_heudiconv.py
# COPY create_archive.py /flywheel/v0/create_archive.py
# COPY create_archive_funcs.py /flywheel/v0/create_archive_funcs.py
RUN chmod +x ${FLYWHEEL}/*


############################
# ENV preservation for Flywheel Engine
RUN env -u HOSTNAME -u PWD | \
  awk -F = '{ print "export " $1 "=\"" $2 "\"" }' > ${FLYWHEEL}/docker-env.sh

WORKDIR /flywheel/v0
